"""Checkpoint 持久化适配器；状态序列化后写入 Agent 自有 PostgreSQL Schema。"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any, cast

from efficiency_platform_agent.core.checkpoint_erasure import (
    CheckpointResidue,
    ThreadErasurePlan,
)
from efficiency_platform_agent.core.run import JsonObject, JsonValue

from ..providers.database.postgres import PostgresProvider
from .checkpoint import CheckpointRecord
from .contracts import CheckpointView


def _to_json_value(value: object) -> JsonValue:
    """将数据库驱动返回的 JSON 容器转换为框架不可变值。"""

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, JsonObject):
        return value
    if isinstance(value, Mapping):
        return JsonObject(
            tuple((str(key), _to_json_value(item)) for key, item in value.items())
        )
    if isinstance(value, (tuple, list)):
        return tuple(_to_json_value(item) for item in value)
    raise ValueError("CHECKPOINT_FORMAT_INVALID")


class PostgresCheckpointStore:
    """提供与进程内 CheckpointStore 相同的最小保存/读取接口。"""

    backend_id = "owned"

    def __init__(self, connection: Any, schema: str) -> None:
        self.provider = PostgresProvider(
            connection, schema, allow_runtime_schema=True
        )

    async def save(
        self,
        run_id: str,
        checkpoint_ns: str,
        state: dict[str, Any],
        *,
        tenant_id: str = "",
        resume_binding: JsonObject | None = None,
        checkpoint_id: str | None = None,
    ) -> CheckpointView:
        cid = checkpoint_id or str(uuid.uuid4())
        await self.provider.save_checkpoint(
            run_id, tenant_id, checkpoint_ns, cid, state
        )
        return CheckpointView(
            run_id, checkpoint_ns, cid, resume_binding or JsonObject()
        )

    async def get(
        self, run_id: str, checkpoint_ns: str, tenant_id: str = ""
    ) -> CheckpointRecord | None:
        """读取并恢复 GraphRuntime 所需的标准 CheckpointRecord。"""

        rows = await self.provider.connection.execute(
            f"SELECT checkpoint_id, state FROM {self.provider.schema}.checkpoints "
            "WHERE thread_id = %s AND checkpoint_ns = %s AND tenant_id = %s",
            (run_id, checkpoint_ns, tenant_id),
        )
        if hasattr(rows, "__await__"):
            rows = await rows
        if hasattr(rows, "fetchone"):
            row = rows.fetchone()
            if hasattr(row, "__await__"):
                row = await row
        else:
            row = (rows or [None])[0]
        if row is None:
            return None
        if isinstance(row, Mapping):
            checkpoint_id = row.get("checkpoint_id")
            state = row.get("state")
        elif isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
            if len(row) < 2:
                raise ValueError("CHECKPOINT_FORMAT_INVALID")
            checkpoint_id, state = row[0], row[1]
        else:
            raise TypeError("CHECKPOINT_FORMAT_INVALID")
        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            raise TypeError("CHECKPOINT_FORMAT_INVALID")
        if not isinstance(state, Mapping):
            raise TypeError("CHECKPOINT_FORMAT_INVALID")
        normalized_state = {
            str(key): _to_json_value(value) for key, value in state.items()
        }
        binding_value = normalized_state.get("resume_binding", JsonObject())
        binding = (
            binding_value if isinstance(binding_value, JsonObject) else JsonObject()
        )
        return CheckpointRecord(
            CheckpointView(run_id, checkpoint_ns, checkpoint_id, binding),
            normalized_state,
        )

    async def close(self) -> None:
        """释放注入连接或连接池。"""
        await self.provider.close()

    async def delete_thread(
        self,
        thread_id: str,
        tenant_id: str,
        *,
        authorization: ThreadErasurePlan | None = None,
    ) -> None:
        """只删除本租户整 thread；自有表不存官方 blobs/writes。"""
        connection = _erasure_connection(self.provider.connection)
        await connection.execute(
            f"DELETE FROM {self.provider.schema}.checkpoints "
            "WHERE tenant_id = %s AND thread_id = %s",
            (tenant_id, thread_id),
        )
        _erasure_connection(connection)

    async def remaining(
        self,
        thread_id: str,
        tenant_id: str,
        *,
        authorization: ThreadErasurePlan | None = None,
    ) -> CheckpointResidue:
        connection = _erasure_connection(self.provider.connection)
        cursor = await connection.execute(
            f"SELECT count(*) AS checkpoints FROM {self.provider.schema}.checkpoints "
            "WHERE tenant_id = %s AND thread_id = %s",
            (tenant_id, thread_id),
        )
        row = await cursor.fetchone()
        _erasure_connection(connection)
        count = row["checkpoints"] if isinstance(row, Mapping) else row[0]
        return CheckpointResidue(count, 0, 0)


def create_async_postgres_saver(pool: Any) -> Any:
    """组合 LangGraph 官方 AsyncPostgresSaver；setup 生命周期由显式脚本负责。"""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    return AsyncPostgresSaver(pool)


class OfficialPostgresThreadStore:
    """锁定官方 3.1.2；只支持注入的专用 autocommit 真实连接。"""

    backend_id = "official"

    def __init__(self, saver: Any) -> None:
        from importlib.metadata import version

        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        if type(saver) is not AsyncPostgresSaver:
            raise TypeError("OFFICIAL_POSTGRES_SAVER_REQUIRED")
        if version("langgraph-checkpoint-postgres") != "3.1.2":
            raise ValueError("POSTGRES_SAVER_VERSION_UNVERIFIED")
        self._saver = saver
        self._connection()

    def _connection(self) -> Any:
        if self._saver.pipe is not None:
            raise ValueError("POSTGRES_ERASURE_PIPELINE_UNSUPPORTED")
        return _erasure_connection(self._saver.conn)

    async def delete_thread(
        self,
        thread_id: str,
        tenant_id: str,
        *,
        authorization: ThreadErasurePlan | None = None,
    ) -> None:
        _authorize_official_thread(authorization, thread_id, tenant_id)
        self._connection()
        await self._saver.adelete_thread(thread_id)
        self._connection()

    async def remaining(
        self,
        thread_id: str,
        tenant_id: str,
        *,
        authorization: ThreadErasurePlan | None = None,
    ) -> CheckpointResidue:
        _authorize_official_thread(authorization, thread_id, tenant_id)
        self._connection()
        # 与官方删除共用连接和 search_path，避免验证另一个库或 namespace。
        async with self._saver._cursor() as cursor:
            await cursor.execute(
                "SELECT (SELECT count(*) FROM checkpoints WHERE thread_id = %s) AS checkpoints, "
                "(SELECT count(*) FROM checkpoint_blobs WHERE thread_id = %s) AS blobs, "
                "(SELECT count(*) FROM checkpoint_writes WHERE thread_id = %s) AS writes",
                (thread_id, thread_id, thread_id),
            )
            row = cast(Mapping[str, int], await cursor.fetchone())
        self._connection()
        return CheckpointResidue(row["checkpoints"], row["blobs"], row["writes"])


def _authorize_official_thread(
    plan: ThreadErasurePlan | None, thread_id: str, tenant_id: str
) -> None:
    if (
        plan is None
        or plan.scope.conversation.tenant_id != tenant_id
        or not plan.unique_owner
        or not plan.registry_complete
        or not plan.write_fenced
        or plan.gate_state not in {"BLOCKED", "REVOKED"}
        or thread_id not in {thread.thread_id for thread in plan.threads}
    ):
        raise PermissionError("ERASURE_THREAD_NOT_AUTHORIZED")


def _erasure_connection(connection: Any) -> Any:
    from psycopg import AsyncConnection

    if not isinstance(connection, AsyncConnection):
        raise TypeError("REAL_POSTGRES_DRIVER_REQUIRED")
    _check_erasure_connection_state(connection)
    return connection


def _check_erasure_connection_state(connection: Any) -> None:
    """只读取连接状态；真实驱动类型由调用边界另外强制校验。"""
    if not connection.autocommit:
        raise ValueError("POSTGRES_ERASURE_AUTOCOMMIT_REQUIRED")
    from psycopg.pq import PipelineStatus, TransactionStatus

    if connection.info.pipeline_status != PipelineStatus.OFF:
        raise ValueError("POSTGRES_ERASURE_PIPELINE_UNSUPPORTED")
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError("POSTGRES_ERASURE_IDLE_REQUIRED")


__all__ = [
    "OfficialPostgresThreadStore",
    "PostgresCheckpointStore",
    "create_async_postgres_saver",
]
