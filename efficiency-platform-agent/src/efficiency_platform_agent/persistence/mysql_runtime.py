"""Agent Run/Event 的异步 MySQL 持久化适配器。"""

from __future__ import annotations

import time
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from efficiency_platform_agent.configuration.runtime_database import (
    validate_runtime_database_url,
)
from efficiency_platform_agent.core.runtime import RunEventRecord, RunRecord

from .mysql_codec import decode_event, decode_run, encode_event, encode_run


class MySqlPersistenceError(ValueError):
    """稳定的运行态持久化错误。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class MySqlRuntimeDatabase:
    """共享异步连接池，并为健康检查和关闭提供单一边界。"""

    def __init__(self, database_url: str) -> None:
        self.engine = create_async_engine(
            validate_runtime_database_url(database_url),
            pool_pre_ping=True,
            pool_recycle=1_800,
        )

    async def ping(self) -> None:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            raise RuntimeError("RUNTIME_DATABASE_UNAVAILABLE") from error

    async def close(self) -> None:
        await self.engine.dispose()


class MySqlRunRepository:
    """使用完整 JSON 快照和版本条件保存 Run。"""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def create(self, record: RunRecord) -> None:
        now = int(time.time() * 1000)
        try:
            async with self.engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO agent_run "
                        "(run_id,tenant_id,request_id,status,version,state_json,"
                        "created_at_epoch_ms,updated_at_epoch_ms) "
                        "VALUES (:run_id,:tenant_id,:request_id,:status,:version,"
                        "CAST(:state_json AS JSON),:created_at,:updated_at)"
                    ),
                    {
                        "run_id": record.run_id,
                        "tenant_id": record.request.tenant_id,
                        "request_id": record.request.request_id,
                        "status": record.status.value,
                        "version": record.version,
                        "state_json": encode_run(record),
                        "created_at": now,
                        "updated_at": now,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO agent_request_deduplication "
                        "(tenant_id,request_id,run_id,created_at_epoch_ms) "
                        "VALUES (:tenant_id,:request_id,:run_id,:created_at)"
                    ),
                    {
                        "tenant_id": record.request.tenant_id,
                        "request_id": record.request.request_id,
                        "run_id": record.run_id,
                        "created_at": now,
                    },
                )
        except IntegrityError as error:
            raise MySqlPersistenceError(
                "RUN_ALREADY_EXISTS", "Run 或 request_id 已存在"
            ) from error

    async def get(self, run_id: str, tenant_id: str) -> RunRecord | None:
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT state_json FROM agent_run "
                    "WHERE run_id=:run_id AND tenant_id=:tenant_id"
                ),
                {"run_id": run_id, "tenant_id": tenant_id},
            )
            value = result.scalar_one_or_none()
        return None if value is None else decode_run(value)

    async def get_by_request_id(
        self, request_id: str, tenant_id: str
    ) -> RunRecord | None:
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT state_json FROM agent_run "
                    "WHERE request_id=:request_id AND tenant_id=:tenant_id"
                ),
                {"request_id": request_id, "tenant_id": tenant_id},
            )
            value = result.scalar_one_or_none()
        return None if value is None else decode_run(value)

    async def save(self, record: RunRecord, expected_version: int) -> None:
        if record.version != expected_version + 1:
            raise MySqlPersistenceError("RUN_VERSION_CONFLICT", "Run 版本条件无效")
        async with self.engine.begin() as connection:
            result = await connection.execute(
                text(
                    "UPDATE agent_run SET status=:status,version=:next_version,"
                    "state_json=CAST(:state_json AS JSON),updated_at_epoch_ms=:updated_at "
                    "WHERE run_id=:run_id AND tenant_id=:tenant_id AND version=:expected_version"
                ),
                {
                    "status": record.status.value,
                    "next_version": record.version,
                    "state_json": encode_run(record),
                    "updated_at": int(time.time() * 1000),
                    "run_id": record.run_id,
                    "tenant_id": record.request.tenant_id,
                    "expected_version": expected_version,
                },
            )
            if result.rowcount != 1:
                raise MySqlPersistenceError("RUN_VERSION_CONFLICT", "Run 版本冲突")


class MySqlRunEventStore:
    """锁定所属 Run 后按连续序号追加事件。"""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def append(self, event: RunEventRecord) -> None:
        try:
            async with self.engine.begin() as connection:
                run = await connection.execute(
                    text(
                        "SELECT run_id FROM agent_run "
                        "WHERE run_id=:run_id AND tenant_id=:tenant_id FOR UPDATE"
                    ),
                    {"run_id": event.run_id, "tenant_id": event.tenant_id},
                )
                if run.scalar_one_or_none() is None:
                    raise MySqlPersistenceError("RUN_NOT_FOUND", "Run 不存在")
                current = await connection.execute(
                    text(
                        "SELECT COALESCE(MAX(sequence_no),0) FROM agent_run_event "
                        "WHERE run_id=:run_id AND tenant_id=:tenant_id"
                    ),
                    {"run_id": event.run_id, "tenant_id": event.tenant_id},
                )
                expected = int(current.scalar_one()) + 1
                if event.sequence != expected:
                    raise MySqlPersistenceError(
                        "EVENT_SEQUENCE_CONFLICT", "事件序号不连续"
                    )
                await connection.execute(
                    text(
                        "INSERT INTO agent_run_event "
                        "(event_id,run_id,tenant_id,sequence_no,event_type,status,"
                        "occurred_at_epoch_ms,event_json) VALUES "
                        "(:event_id,:run_id,:tenant_id,:sequence_no,:event_type,:status,"
                        ":occurred_at,CAST(:event_json AS JSON))"
                    ),
                    {
                        "event_id": event.event_id,
                        "run_id": event.run_id,
                        "tenant_id": event.tenant_id,
                        "sequence_no": event.sequence,
                        "event_type": event.event_type,
                        "status": event.status.value,
                        "occurred_at": event.occurred_at_epoch_ms,
                        "event_json": encode_event(event),
                    },
                )
        except IntegrityError as error:
            raise MySqlPersistenceError(
                "EVENT_ID_CONFLICT", "事件 ID 或序号已存在"
            ) from error

    async def list_after(
        self, run_id: str, tenant_id: str, after_sequence: int
    ) -> Sequence[RunEventRecord]:
        if after_sequence < 0:
            raise ValueError("after_sequence 必须是非负整数")
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT event_json FROM agent_run_event "
                    "WHERE run_id=:run_id AND tenant_id=:tenant_id "
                    "AND sequence_no>:after_sequence ORDER BY sequence_no"
                ),
                {
                    "run_id": run_id,
                    "tenant_id": tenant_id,
                    "after_sequence": after_sequence,
                },
            )
            return tuple(decode_event(row[0]) for row in result.fetchall())


__all__ = [
    "MySqlPersistenceError",
    "MySqlRunEventStore",
    "MySqlRunRepository",
    "MySqlRuntimeDatabase",
]
