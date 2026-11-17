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
        publication.published(), publication.execution_agents
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
    try:
        manifest = MySqlContextManifestStore(database.engine)
        dispatch = ContextDispatch(
            ContextController(ConservativeRequestTokenCounter(), manifest, key),
            manifest,
            authority,
            stage_store=MySqlContextStageStore(database.engine, key),
            hmac_key=key,
        )
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
            )
        return build_local_agent_application(
            settings=resolved,
            context_dispatch=dispatch,
            memory_runtime=memory,
            memory_database=database,
        )
    except BaseException:
        try:
            if memory is not None:
                await memory.close()
        finally:
            await database.close()
        raise
