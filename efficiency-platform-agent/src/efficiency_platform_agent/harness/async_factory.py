"""在服务事件循环内装配记忆依赖；失败时关闭本次拥有的连接，不迁移数据库。"""

from __future__ import annotations

import base64
import re
from pathlib import Path

from efficiency_platform_agent.configuration.context_publication import (
    load_context_publication,
)
from efficiency_platform_agent.configuration.integration import S7IntegrationSettings
from efficiency_platform_agent.context.controller import ContextController
from efficiency_platform_agent.context.dispatch import ContextDispatch
from efficiency_platform_agent.persistence.context_manifest import (
    MySqlContextManifestStore,
)
from efficiency_platform_agent.persistence.context_stage import MySqlContextStageStore
from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher
from efficiency_platform_agent.persistence.mysql_runtime import MySqlRuntimeDatabase
from efficiency_platform_agent.providers.database.postgres import (
    validate_agent_owned_schema,
)
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)

from .context_authority import ServerDispatchAuthority
from .local_real_factory import LocalAgentApplication, build_local_agent_application
from .memory_runtime import MemoryRuntimeComponents, build_memory_runtime


def _secret(settings: S7IntegrationSettings, name: str) -> str:
    value = getattr(settings, name)
    if value is None or not value.get_secret_value().strip():
        raise ValueError("MEMORY_RUNTIME_CONFIGURATION_REQUIRED")
    return value.get_secret_value()


async def build_async_local_agent_application(
    settings: S7IntegrationSettings | None = None, *, env_file: str | Path = ".env"
) -> LocalAgentApplication:
    resolved = settings or S7IntegrationSettings.from_env_file(env_file)
    if not resolved.context_enabled:
        return build_local_agent_application(settings=resolved)
    publication = load_context_publication(resolved.context_publication_file)
    authority = ServerDispatchAuthority(
        publication.published(),
        publication.execution_agents,
        specialist_lineage_enabled=publication.specialist_lineage_enabled,
    )
    authority.assert_ready()
    key = _secret(resolved, "context_hmac_key").encode()
    checkpoint_key = b""
    if resolved.memory_enabled:
        validate_agent_owned_schema(resolved.memory_owned_checkpoint_schema)
        for name in (
            resolved.memory_registry_schema,
            resolved.memory_official_checkpoint_schema,
            resolved.memory_owned_checkpoint_schema,
        ):
            if not re.fullmatch(r"(?:agent_runtime|memory_it)_[a-z0-9_]+", name):
                raise ValueError("MEMORY_RUNTIME_SCHEMA_REQUIRED")
        if (
            len(
                {
                    resolved.memory_registry_schema,
                    resolved.memory_official_checkpoint_schema,
                    resolved.memory_owned_checkpoint_schema,
                }
            )
            != 3
        ):
            raise ValueError("MEMORY_RUNTIME_SCHEMA_REQUIRED")
        try:
            checkpoint_key = base64.b64decode(
                _secret(resolved, "memory_checkpoint_encryption_key"), validate=True
            )
        except ValueError:
            raise ValueError("MEMORY_CHECKPOINT_KEY_REQUIRED") from None
        if (
            len(checkpoint_key) != 32
            or not resolved.memory_checkpoint_encryption_key_version
        ):
            raise ValueError("MEMORY_CHECKPOINT_KEY_REQUIRED")
        _secret(resolved, "memory_postgres_dsn")
    database = MySqlRuntimeDatabase(_secret(resolved, "runtime_database_url"))
    memory: MemoryRuntimeComponents | None = None
    index_provider = None
    cleanup_connection = None
    try:
        if resolved.memory_enabled:
            memory_key = base64.b64decode(
                _secret(resolved, "memory_encryption_key"), validate=True
            )
            cipher = MemorySnapshotCipher(
                resolved.memory_encryption_key_version,
                {resolved.memory_encryption_key_version: memory_key},
            )
            memory = await build_memory_runtime(
                engine=database.engine,
                memory_cipher=cipher,
                checkpoint_key=checkpoint_key,
                checkpoint_key_version=resolved.memory_checkpoint_encryption_key_version,
                postgres_dsn=_secret(resolved, "memory_postgres_dsn"),
                registry_schema=resolved.memory_registry_schema,
                official_schema=resolved.memory_official_checkpoint_schema,
                owned_schema=resolved.memory_owned_checkpoint_schema,
                refresh_enabled=resolved.memory_refresh_enabled,
            )
            if resolved.memory_refresh_enabled and (
                memory.refresh_service is None or memory.send_authority is None
            ):
                raise ValueError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        if (
            resolved.memory_index_enabled
            or resolved.memory_recall_enabled
            or resolved.memory_index_cleanup_enabled
        ):
            from psycopg import AsyncConnection
            from psycopg.rows import tuple_row

            from efficiency_platform_agent.providers.database.postgres import (
                PostgresProvider,
            )

            connection = await AsyncConnection.connect(
                _secret(resolved, "memory_postgres_dsn"),
                autocommit=True,
                prepare_threshold=0,
                row_factory=tuple_row,
                connect_timeout=5,
            )
            if memory is not None:
                memory.connections += (connection,)
            else:
                cleanup_connection = connection
            index_provider = PostgresProvider(
                connection, resolved.memory_index_schema, allow_runtime_schema=True
            )
            schema = index_provider.schema
            for table, columns in {
                "memory_index_entries": "scope_key,embedding_model,dimension,policy_version,item_id,generation,version_id,deletion_epoch,source_fingerprint,embedding,terms,expires_at",
                "memory_index_fences": "scope_key,item_id,generation,deletion_epoch,deleted,forget_epoch",
                "memory_index_task_slots": "tenant_id,task_id,operation_id,fingerprint",
                "memory_index_jobs": "scope_key,embedding_model,dimension,policy_version,item_id,generation,version_id,deletion_epoch,source_fingerprint,fingerprint,token,state,operation_id,event_id,created_at",
                "memory_query_operations": "tenant_id,task_id,scope_key,embedding_model,dimension,policy_version,query_hash,fingerprint,token,state,operation_id,embedding,item_refs,created_at,expires_at",
            }.items():
                await connection.execute(
                    f"SELECT {columns} FROM {schema}.{table} LIMIT 0"
                )
            checks = await (
                await connection.execute(
                    "SELECT COUNT(*) FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname=%s AND (t.relname LIKE 'memory_index_%%' OR t.relname='memory_query_operations') AND c.contype='p' AND c.convalidated",
                    (schema,),
                )
            ).fetchone()
            if checks is None or checks[0] != 5:
                raise ValueError("MEMORY_INDEX_SCHEMA_REQUIRED")
        manifest = MySqlContextManifestStore(
            database.engine,
            memory_execution_store=memory.store.store
            if memory is not None and resolved.memory_refresh_enabled
            else None,
        )
        summary_context = None
        if resolved.memory_summary_enabled:
            if memory is None:
                raise ValueError("MEMORY_AUTHORITY_REQUIRED")
            from .bound_summary_context import BoundMemorySummaryContext

            summary_context = BoundMemorySummaryContext(memory.store)
            authority.summary_context_port = summary_context
        dispatch = ContextDispatch(
            ContextController(
                ConservativeRequestTokenCounter(),
                manifest,
                key,
                summary_context_port=summary_context,
            ),
            manifest,
            authority,
            stage_store=MySqlContextStageStore(database.engine, key),
            hmac_key=key,
        )
        if memory is not None and resolved.memory_refresh_enabled:
            if memory.send_authority is None:
                raise ValueError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
            manifest.install_result_authority(memory.send_authority)
        application = build_local_agent_application(
            settings=resolved,
            context_dispatch=dispatch,
            memory_runtime=memory,
            memory_database=database,
            memory_index_provider=index_provider,
        )
        if cleanup_connection is not None:
            application.customer_service_resources += (cleanup_connection,)
        return application
    except BaseException:
        try:
            if cleanup_connection is not None:
                await cleanup_connection.close()
            if memory is not None:
                await memory.close()
        finally:
            await database.close()
        raise
