"""Intent V2 revision CAS 的 PostgreSQL 权威存储。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg.types.json import Jsonb

from efficiency_platform_agent.contracts.intent_v2 import IntentFrameV2

from ._postgres import ensure_writes_enabled, fetchone, validate_runtime_schema


@dataclass(frozen=True, slots=True)
class IntentStateScope:
    tenant_id: str

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or len(self.tenant_id) > 128:
            raise ValueError("tenant_id 必须是非空且有界字符串")


class PostgresIntentStateRepository:
    """按 tenant/task 复合键隔离并以 revision 执行 CAS。"""

    def __init__(self, connection: Any, schema: str = "agent_runtime") -> None:
        self.connection = connection
        self.schema = validate_runtime_schema(schema)

    async def get(self, scope: IntentStateScope, task_id: str) -> IntentFrameV2 | None:
        _task_id(task_id)
        row = await fetchone(
            self.connection,
            f"SELECT frame FROM {self.schema}.intent_states "
            "WHERE tenant_id=%s AND task_id=%s",
            (scope.tenant_id, task_id),
        )
        return None if row is None else IntentFrameV2.model_validate(row[0])

    async def compare_and_set(
        self,
        scope: IntentStateScope,
        expected_revision: int,
        frame: IntentFrameV2,
    ) -> bool:
        if expected_revision < 0 or isinstance(expected_revision, bool):
            raise ValueError("expected_revision 必须是非负整数")
        if frame.revision != expected_revision + 1:
            raise ValueError("frame.revision 必须等于 expected_revision + 1")
        async with self.connection.transaction():
            await ensure_writes_enabled(self.connection, self.schema)
            payload = Jsonb(frame.model_dump(mode="json"))
            if expected_revision == 0:
                cursor = await self.connection.execute(
                    f"INSERT INTO {self.schema}.intent_states "
                    "(tenant_id,task_id,revision,frame) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (tenant_id,task_id) DO NOTHING",
                    (scope.tenant_id, frame.task_id, frame.revision, payload),
                )
            else:
                cursor = await self.connection.execute(
                    f"UPDATE {self.schema}.intent_states "
                    "SET revision=%s, frame=%s, updated_at=clock_timestamp() "
                    "WHERE tenant_id=%s AND task_id=%s AND revision=%s",
                    (
                        frame.revision,
                        payload,
                        scope.tenant_id,
                        frame.task_id,
                        expected_revision,
                    ),
                )
            return cursor.rowcount == 1


def _task_id(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError("task_id 必须是非空且有界字符串")


IntentStateRepository = PostgresIntentStateRepository

__all__ = [
    "IntentStateRepository",
    "IntentStateScope",
    "PostgresIntentStateRepository",
]
