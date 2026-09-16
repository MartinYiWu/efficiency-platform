"""Checkpoint 持久化适配器；状态序列化后写入 Agent 自有 PostgreSQL Schema。"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

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

    def __init__(self, connection: Any, schema: str) -> None:
        self.provider = PostgresProvider(connection, schema)

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


def create_async_postgres_saver(pool: Any) -> Any:
    """组合 LangGraph 官方 AsyncPostgresSaver；setup 生命周期由显式脚本负责。"""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    return AsyncPostgresSaver(pool)


__all__ = ["PostgresCheckpointStore", "create_async_postgres_saver"]
