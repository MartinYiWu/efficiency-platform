"""同一事件循环的正式记忆组合；只读检查已部署schema，不执行DDL。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from efficiency_platform_agent.core.memory import ExecutionScope
from efficiency_platform_agent.memory.checkpoint_erasure import CheckpointEraser
from efficiency_platform_agent.memory.execution_bindings import ThreadErasureService
from efficiency_platform_agent.orchestration.fenced_checkpoint import (
    CheckpointPayloadSerializer,
    FencedCheckpointSaver,
    OfficialPostgresInventory,
    OwnedPostgresInventory,
)
from efficiency_platform_agent.orchestration.memory_saver_factory import (
    create_official_saver,
)
from efficiency_platform_agent.orchestration.postgres_checkpoint import (
    OfficialPostgresThreadStore,
    PostgresCheckpointStore,
)
from efficiency_platform_agent.persistence.memory_checkpoint_cipher import (
    AesGcmCheckpointBodyCipher,
)
from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher
from efficiency_platform_agent.persistence.memory_cleanup import (
    MySqlMemoryCleanupJournal,
)
from efficiency_platform_agent.persistence.memory_execution import (
    MySqlMemoryExecutionStore,
)
from efficiency_platform_agent.persistence.memory_execution_registry import (
    PostgresMemoryExecutionRegistry,
)
from efficiency_platform_agent.persistence.memory_source_epoch import (
    MySqlExecutionSourceEpochAuthority,
)
from efficiency_platform_agent.providers.database.postgres import (
    validate_agent_owned_schema,
)

if TYPE_CHECKING:
    from efficiency_platform_agent.memory.context_refresh import (
        MemoryContextRefreshService,
    )


def build_memory_binding_updater(direct_gate, customer_service):
    async def update(original_record, refreshed_context) -> bool:
        if original_record.runtime_kind == "OPERATIONS" and direct_gate is not None:
            return (
                await direct_gate.update_wait_frame_binding(
                    original_record, refreshed_context
                )
                is True
            )
        if (
            original_record.runtime_kind == "CUSTOMER_SERVICE"
            and customer_service is not None
        ):
            return (
                await customer_service.refresh_memory_binding(
                    original_record, refreshed_context
                )
                is True
            )
        return False

    return update


class RegisteredMemoryExecutionStore:
    def __init__(
        self,
        store: MySqlMemoryExecutionStore,
        registry: PostgresMemoryExecutionRegistry,
    ):
        self.store, self.registry = store, registry

    async def get(self, tenant_id, execution_id):
        return await self.store.get(tenant_id, execution_id)

    async def invalidate(self, event):
        return await self.store.invalidate(event)

    async def claim(
        self, context, runtime_id, runtime_kind, request_fingerprint, budget_deadline
    ):
        record, created = await self.store.claim(
            context, runtime_id, runtime_kind, request_fingerprint, budget_deadline
        )
        node = {
            "OPERATIONS": "direct",
            "CUSTOMER_SERVICE": "customer-service:answer_general",
        }.get(runtime_kind)
        grant = next(
            (item for item in context.execution_grants if item.node_id == node), None
        )
        if grant is None:
            raise ValueError("MEMORY_RUNTIME_CAPABILITY_UNSUPPORTED")
        packet = context.packet
        scope = ExecutionScope(
            packet.scope,
            packet.task_id,
            packet.execution_id,
            grant.node_id,
            grant.purpose,
            grant.execution_agent_id,
        )
        if runtime_kind == "CUSTOMER_SERVICE":
            await self.registry.enroll_no_checkpoint(scope, record.runtime_id)
        else:
            await self.registry.enroll(scope, record.runtime_id)
        return record, created


@dataclass
class MemoryRuntimeComponents:
    store: RegisteredMemoryExecutionStore
    registry: PostgresMemoryExecutionRegistry
    saver: FencedCheckpointSaver
    owned: PostgresCheckpointStore
    serializer: CheckpointPayloadSerializer
    erasure: ThreadErasureService
    journal: MySqlMemoryCleanupJournal
    connections: tuple[AsyncConnection[Any], ...]
    refresh_service: MemoryContextRefreshService | None = None
    send_authority: Any | None = None

    async def close(self):
        for connection in reversed(self.connections):
            await connection.close()


async def build_memory_runtime(
    *,
    engine: AsyncEngine,
    memory_cipher: MemorySnapshotCipher,
    checkpoint_key: bytes,
    checkpoint_key_version: str,
    postgres_dsn: str,
    registry_schema: str,
    official_schema: str,
    owned_schema: str,
    refresh_enabled: bool = False,
) -> MemoryRuntimeComponents:
    validate_agent_owned_schema(owned_schema)
    if len({registry_schema, official_schema, owned_schema}) != 3 or any(
        not re.fullmatch(r"(?:agent_runtime|memory_it)_[a-z0-9_]+", name)
        for name in (registry_schema, official_schema)
    ):
        raise ValueError("MEMORY_RUNTIME_SCHEMA_REQUIRED")
    serializer = CheckpointPayloadSerializer(
        AesGcmCheckpointBodyCipher(checkpoint_key, checkpoint_key_version)
    )
    async with engine.connect() as mysql_connection:
        await mysql_connection.execute(
            text(
                "SELECT state,snapshot_ciphertext,snapshot_nonce,scrub_event_id,scrub_authority FROM agent_memory_execution LIMIT 0"
            )
        )
        await mysql_connection.execute(
            text(
                "SELECT cleanup_fingerprint,stop_confirmed,threads_receipt,scrub_receipt,expected_execution_revision,grant_epoch,source_epoch,deletion_epoch FROM agent_memory_invalidation_receipt LIMIT 0"
            )
        )
        checks = (
            await mysql_connection.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_schema=DATABASE() AND table_name='agent_memory_execution' AND constraint_name IN ('ck_memory_execution_state','ck_memory_execution_body') AND constraint_type='CHECK' AND enforced='YES'"
                )
            )
        ).scalar_one()
        trigger = (
            await mysql_connection.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name='trg_memory_execution_scrub' AND event_object_table='agent_memory_execution'"
                )
            )
        ).scalar_one()
        if checks != 2 or trigger != 1:
            raise ValueError("MEMORY_SCRUB_SCHEMA_REQUIRED")
        has_refresh_schema = (
            await mysql_connection.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='agent_memory_execution' AND column_name='current_context_fingerprint'"
                )
            )
        ).scalar_one() == 1
        if refresh_enabled and not has_refresh_schema:
            raise ValueError("MEMORY_REFRESH_SCHEMA_REQUIRED")
        if has_refresh_schema:
            refresh_columns = set(
                (
                    await mysql_connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='agent_memory_context_refresh'"
                        )
                    )
                ).scalars()
            )
            if not {
                "record_kind",
                "phase",
                "body_ciphertext",
                "body_scrub_event_id",
            }.issubset(refresh_columns):
                raise ValueError("MEMORY_REFRESH_SCHEMA_REQUIRED")
            await mysql_connection.execute(
                text(
                    "SELECT current_context_fingerprint FROM agent_memory_execution LIMIT 0"
                )
            )
            await mysql_connection.execute(
                text(
                    "SELECT record_kind,phase,body_ciphertext,body_scrub_event_id FROM agent_memory_context_refresh LIMIT 0"
                )
            )
        if refresh_enabled:
            required_checks = {
                "ck_memory_execution_current_fp",
                "ck_memory_refresh_ids",
                "ck_memory_refresh_scope",
                "ck_memory_refresh_attempt",
                "ck_memory_refresh_hashes",
                "ck_memory_refresh_stage",
                "ck_memory_refresh_body",
                "ck_memory_refresh_kind",
                "ck_memory_refresh_hmac",
                "ck_memory_refresh_checkpoint",
                "ck_memory_refresh_resume_start",
                "ck_memory_refresh_receipt_code",
                "ck_memory_refresh_receipt",
                "ck_memory_refresh_receipt_phase",
                "ck_memory_refresh_ordinal",
                "ck_memory_refresh_next_wait",
            }
            actual_checks = set(
                (
                    await mysql_connection.execute(
                        text(
                            "SELECT constraint_name FROM information_schema.table_constraints WHERE constraint_schema=DATABASE() AND table_name IN ('agent_memory_execution','agent_memory_context_refresh') AND constraint_type='CHECK' AND enforced='YES'"
                        )
                    )
                ).scalars()
            )
            actual_triggers = set(
                await mysql_connection.execute(
                    text(
                        "SELECT trigger_name,event_object_table,event_manipulation FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND action_timing='BEFORE'"
                    )
                )
            )
            required_triggers = {
                ("trg_memory_refresh_insert", "agent_memory_context_refresh", "INSERT"),
                ("trg_memory_refresh_update", "agent_memory_context_refresh", "UPDATE"),
                ("trg_memory_refresh_delete", "agent_memory_context_refresh", "DELETE"),
                ("trg_memory_execution_refresh", "agent_memory_execution", "UPDATE"),
            }
            unique_indexes = set(
                (
                    await mysql_connection.execute(
                        text(
                            "SELECT index_name FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='agent_memory_context_refresh' AND non_unique=0 AND sub_part IS NULL GROUP BY index_name"
                        )
                    )
                ).scalars()
            )
            if (
                not required_checks.issubset(actual_checks)
                or not required_triggers.issubset(actual_triggers)
                or not {
                    "PRIMARY",
                    "uk_memory_refresh_open_wait",
                    "uk_memory_refresh_pending",
                    "uk_memory_refresh_result",
                }.issubset(unique_indexes)
            ):
                raise ValueError("MEMORY_REFRESH_SCHEMA_REQUIRED")
    connections = []
    try:
        for schema in (
            registry_schema,
            official_schema,
            owned_schema,
            official_schema,
            owned_schema,
        ):
            connection = await AsyncConnection.connect(
                postgres_dsn,
                autocommit=True,
                prepare_threshold=0,
                row_factory=dict_row,
                connect_timeout=5,
            )
            connections.append(connection)
            await connection.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
            )
        (
            registry_connection,
            normal_official,
            normal_owned,
            delete_official,
            delete_owned,
        ) = connections
        # 所有实际后端与registry delta必须已部署；从不存在的表不能推断无线程。
        for name in (
            "agent_memory_thread_execution",
            "agent_memory_thread_member",
            "agent_memory_thread_namespace",
            "agent_memory_thread_resume",
        ):
            await registry_connection.execute(
                sql.SQL("SELECT 1 FROM {} LIMIT 0").format(
                    sql.Identifier(registry_schema, name)
                )
            )
        await registry_connection.execute(
            sql.SQL("SELECT checkpoint_mode FROM {} LIMIT 0").format(
                sql.Identifier(registry_schema, "agent_memory_thread_execution")
            )
        )
        if refresh_enabled:
            column_cursor = await registry_connection.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name='agent_memory_thread_execution'",
                (registry_schema,),
            )
            refresh_columns = {
                row["column_name"] for row in await column_cursor.fetchall()
            }
            if not {
                "current_context_fingerprint",
                "wait_status",
                "pending_resume_request_id",
            }.issubset(refresh_columns):
                raise ValueError("MEMORY_REFRESH_SCHEMA_REQUIRED")
            await registry_connection.execute(
                sql.SQL(
                    "SELECT current_context_fingerprint,wait_status,pending_resume_request_id FROM {} LIMIT 0"
                ).format(
                    sql.Identifier(registry_schema, "agent_memory_thread_execution")
                )
            )
            checks_cursor = await registry_connection.execute(
                "SELECT k.conname FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname IN ('agent_memory_thread_execution','agent_memory_thread_resume') AND k.contype='c' AND k.convalidated",
                (registry_schema,),
            )
            refresh_checks = {row["conname"] for row in await checks_cursor.fetchall()}
            trigger_cursor = await registry_connection.execute(
                "SELECT t.tgname,c.relname,t.tgtype FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND NOT t.tgisinternal AND t.tgenabled IN ('O','A')",
                (registry_schema,),
            )
            refresh_triggers = {
                (row["tgname"], row["relname"], row["tgtype"])
                for row in await trigger_cursor.fetchall()
            }
            index_cursor = await registry_connection.execute(
                "SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname=%s AND t.relname='agent_memory_thread_resume' AND i.indisunique AND i.indisvalid AND i.indisready",
                (registry_schema,),
            )
            refresh_indexes = {row["relname"] for row in await index_cursor.fetchall()}
            if (
                not {
                    "ck_memory_thread_refresh_state",
                    "ck_memory_thread_current_fp",
                    "ck_memory_thread_wait",
                    "ck_memory_thread_pending",
                    "ck_memory_thread_resume_shape",
                    "ck_memory_thread_resume_code",
                    "ck_memory_thread_resume_legacy_code",
                    "ck_memory_thread_resume_key",
                    "ck_memory_thread_resume_phase",
                }.issubset(refresh_checks)
                or not {
                    (
                        "trg_memory_thread_refresh_receipt",
                        "agent_memory_thread_resume",
                        31,
                    ),
                    (
                        "trg_memory_thread_refresh_execution",
                        "agent_memory_thread_execution",
                        27,
                    ),
                }.issubset(refresh_triggers)
                or not {
                    "uk_memory_thread_refresh_candidate",
                    "uk_memory_thread_refresh_pending",
                }.issubset(refresh_indexes)
            ):
                raise ValueError("MEMORY_REFRESH_SCHEMA_REQUIRED")
        for name in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            await normal_official.execute(
                sql.SQL("SELECT 1 FROM {} LIMIT 0").format(
                    sql.Identifier(official_schema, name)
                )
            )
        await normal_owned.execute(
            sql.SQL("SELECT 1 FROM {} LIMIT 0").format(
                sql.Identifier(owned_schema, "checkpoints")
            )
        )
        raw_saver, owned = (
            create_official_saver(normal_official),
            PostgresCheckpointStore(normal_owned, owned_schema),
        )
        original = MySqlMemoryExecutionStore(
            engine, memory_cipher, refresh_schema_required=has_refresh_schema
        )
        registry = PostgresMemoryExecutionRegistry(
            registry_connection,
            registry_schema,
            original,
            MySqlExecutionSourceEpochAuthority(engine, original),
            (OfficialPostgresInventory(raw_saver), OwnedPostgresInventory(owned)),
        )
        erasure = ThreadErasureService(
            registry,
            CheckpointEraser(
                registry,
                (
                    OfficialPostgresThreadStore(create_official_saver(delete_official)),
                    PostgresCheckpointStore(delete_owned, owned_schema),
                ),
            ),
        )
        refresh = None
        send_authority = None
        if refresh_enabled:
            from efficiency_platform_agent.memory.context_refresh import (
                MemoryContextRefreshService,
            )
            from efficiency_platform_agent.persistence.memory_context_refresh import (
                MySqlMemoryContextRefreshStore,
            )

            refresh = MemoryContextRefreshService(
                registry, MySqlMemoryContextRefreshStore(original)
            )
            registry.install_wait_authority(refresh)
            from efficiency_platform_agent.memory.execution_authority import (
                MemorySendLeaseAuthority,
            )

            send_authority = MemorySendLeaseAuthority(registry, original)
            registry.install_result_authority(send_authority)
        return MemoryRuntimeComponents(
            RegisteredMemoryExecutionStore(original, registry),
            registry,
            FencedCheckpointSaver(
                raw_saver, registry, "official", serializer=serializer
            ),
            owned,
            serializer,
            erasure,
            MySqlMemoryCleanupJournal(
                engine, refresh_schema_required=has_refresh_schema
            ),
            tuple(connections),
            refresh,
            send_authority,
        )
    except BaseException:
        for connection in reversed(connections):
            await connection.close()
        raise
