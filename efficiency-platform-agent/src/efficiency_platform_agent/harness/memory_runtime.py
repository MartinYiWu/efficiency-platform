"""同一事件循环的正式记忆组合；只读检查已部署schema，不执行DDL。"""

import re
from dataclasses import dataclass
from typing import Any

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
        original = MySqlMemoryExecutionStore(engine, memory_cipher)
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
        return MemoryRuntimeComponents(
            RegisteredMemoryExecutionStore(original, registry),
            registry,
            FencedCheckpointSaver(
                raw_saver, registry, "official", serializer=serializer
            ),
            owned,
            serializer,
            erasure,
            MySqlMemoryCleanupJournal(engine),
            tuple(connections),
        )
    except BaseException:
        for connection in reversed(connections):
            await connection.close()
        raise
