"""Run/Event 权威存储的 PostgreSQL 参数化实现。"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from efficiency_platform_agent.providers.database.postgres import (
    PostgresConcurrencyError,
    PostgresProvider,
    validate_schema,
)


class PostgresRuntimeRepository:
    """仅访问 Agent 自有 Schema 的运行事实仓储。"""

    def __init__(self, connection: Any, schema: str) -> None:
        self.provider = PostgresProvider(connection, validate_schema(schema))

    async def create(self, record: Any) -> None:
        request = getattr(record, "request", None)
        tenant_id = getattr(request, "tenant_id", "")
        payload = {"status": getattr(getattr(record, "status", None), "value", "")}
        created = await self.provider.save_run(
            record.run_id,
            tenant_id,
            payload,
            record.version,
            getattr(request, "request_id", None),
        )
        if not created:
            raise PostgresConcurrencyError("Run 已存在或租户不匹配")

    async def get(self, run_id: str, tenant_id: str) -> Mapping[str, object] | None:
        rows = await self.provider.connection.execute(
            f"SELECT run_id, tenant_id, payload, version FROM {self.provider.schema}.runs "
            "WHERE run_id = %s AND tenant_id = %s",
            (run_id, tenant_id),
        )
        if hasattr(rows, "__await__"):
            rows = await rows
        return (rows or [None])[0]

    async def get_by_request_id(
        self, request_id: str, tenant_id: str
    ) -> Mapping[str, object] | None:
        rows = await self.provider.connection.execute(
            f"SELECT run_id, tenant_id, payload, version FROM {self.provider.schema}.runs "
            "WHERE request_id = %s AND tenant_id = %s",
            (request_id, tenant_id),
        )
        if hasattr(rows, "__await__"):
            rows = await rows
        return (rows or [None])[0]

    async def save(self, record: Any, expected_version: int) -> None:
        request = getattr(record, "request", None)
        tenant_id = getattr(request, "tenant_id", "")
        payload = {
            "status": getattr(getattr(record, "status", None), "value", ""),
            "output": getattr(record, "output", None),
        }
        updated = await self.provider.save_run(
            record.run_id,
            tenant_id,
            payload,
            expected_version + 1,
            expected_version=expected_version,
        )
        if not updated:
            raise PostgresConcurrencyError("Run 版本冲突")

    async def append(self, event: Any) -> None:
        payload = getattr(event, "payload", event if isinstance(event, Mapping) else {})
        await self.provider.append_event(
            getattr(event, "event_id", str(uuid.uuid4())),
            event.run_id,
            event.tenant_id,
            event.sequence,
            payload,
        )

    async def append_event(
        self, run_id: str, tenant_id: str, payload: Mapping[str, object]
    ) -> None:
        await self.provider.append_event(
            str(uuid.uuid4()), run_id, tenant_id, 1, payload
        )

    async def list_after(
        self, run_id: str, tenant_id: str, after_sequence: int
    ) -> Sequence[Mapping[str, object]]:
        return await self.provider.list_events(run_id, tenant_id, after_sequence)

    async def close(self) -> None:
        """释放注入连接或连接池。"""
        await self.provider.close()


__all__ = ["PostgresRuntimeRepository"]
