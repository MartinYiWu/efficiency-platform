"""Research V2 动作指纹、恢复状态与质量决策的 PostgreSQL 存储。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from psycopg.types.json import Jsonb

from ._postgres import ensure_writes_enabled, fetchone, validate_runtime_schema

type ResearchActionStatus = Literal[
    "IN_PROGRESS", "COMMITTED", "UNKNOWN_OUTCOME", "CANCELLED", "FAILED"
]


@dataclass(frozen=True, slots=True)
class ResearchAction:
    tenant_id: str
    research_id: str
    action_fingerprint: str
    invocation_id: str
    status: ResearchActionStatus
    attempt: int
    request: dict[str, object]
    result: dict[str, object] | None
    conservative_charge: dict[str, object] | None
    lease_owner: str | None
    lease_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class ActionClaim:
    claimed: bool
    action: ResearchAction


class PostgresResearchRepository:
    """动作完成事实优先于 Checkpoint；未知窗口不盲目重放。"""

    def __init__(self, connection: Any, schema: str = "agent_runtime") -> None:
        self.connection = connection
        self.schema = validate_runtime_schema(schema)

    async def claim_action(
        self,
        *,
        tenant_id: str,
        research_id: str,
        action_fingerprint: str,
        invocation_id: str,
        lease_owner: str,
        request: dict[str, object],
        lease_seconds: int = 60,
        allow_unknown_retry: bool = False,
    ) -> ActionClaim:
        _identifiers(
            tenant_id, research_id, action_fingerprint, invocation_id, lease_owner
        )
        if lease_seconds <= 0:
            raise ValueError("lease_seconds 必须为正整数")
        async with self.connection.transaction():
            await ensure_writes_enabled(self.connection, self.schema)
            row = await fetchone(
                self.connection,
                f"SELECT tenant_id,research_id,action_fingerprint,invocation_id,status,"
                "attempt,request,result,conservative_charge,lease_owner,lease_expires_at "
                f"FROM {self.schema}.research_actions "
                "WHERE tenant_id=%s AND research_id=%s AND action_fingerprint=%s "
                "FOR UPDATE",
                (tenant_id, research_id, action_fingerprint),
            )
            if row is None:
                row = await fetchone(
                    self.connection,
                    f"INSERT INTO {self.schema}.research_actions "
                    "(tenant_id,research_id,action_fingerprint,invocation_id,status,"
                    "attempt,request,lease_owner,lease_expires_at) "
                    "VALUES (%s,%s,%s,%s,'IN_PROGRESS',1,%s,%s,"
                    "clock_timestamp()+(%s * interval '1 second')) "
                    "RETURNING tenant_id,research_id,action_fingerprint,invocation_id,"
                    "status,attempt,request,result,conservative_charge,lease_owner,"
                    "lease_expires_at",
                    (
                        tenant_id,
                        research_id,
                        action_fingerprint,
                        invocation_id,
                        Jsonb(request),
                        lease_owner,
                        lease_seconds,
                    ),
                )
                assert row is not None
                return ActionClaim(True, _action(row))
            action = _action(row)
            if action.invocation_id != invocation_id or action.request != request:
                raise RuntimeError("RESEARCH_ACTION_IDEMPOTENCY_CONFLICT")
            if action.status in {"COMMITTED", "CANCELLED", "FAILED"}:
                return ActionClaim(False, action)
            if action.status == "UNKNOWN_OUTCOME" and not allow_unknown_retry:
                return ActionClaim(False, action)
            now = await fetchone(self.connection, "SELECT clock_timestamp()")
            assert now is not None
            if (
                action.status == "IN_PROGRESS"
                and action.lease_expires_at is not None
                and action.lease_expires_at > now[0]
            ):
                return ActionClaim(False, action)
            row = await fetchone(
                self.connection,
                f"UPDATE {self.schema}.research_actions SET status='IN_PROGRESS',"
                "attempt=attempt+1,lease_owner=%s,"
                "lease_expires_at=clock_timestamp()+(%s * interval '1 second'),"
                "updated_at=clock_timestamp() "
                "WHERE tenant_id=%s AND research_id=%s AND action_fingerprint=%s "
                "RETURNING tenant_id,research_id,action_fingerprint,invocation_id,status,"
                "attempt,request,result,conservative_charge,lease_owner,lease_expires_at",
                (
                    lease_owner,
                    lease_seconds,
                    tenant_id,
                    research_id,
                    action_fingerprint,
                ),
            )
            assert row is not None
            return ActionClaim(True, _action(row))

    async def commit_action(
        self,
        *,
        tenant_id: str,
        research_id: str,
        action_fingerprint: str,
        lease_owner: str,
        result: dict[str, object],
    ) -> ResearchAction:
        return await self._finish(
            tenant_id,
            research_id,
            action_fingerprint,
            lease_owner,
            "COMMITTED",
            result=result,
        )

    async def mark_unknown_outcome(
        self,
        *,
        tenant_id: str,
        research_id: str,
        action_fingerprint: str,
        lease_owner: str,
        conservative_charge: dict[str, object],
    ) -> ResearchAction:
        return await self._finish(
            tenant_id,
            research_id,
            action_fingerprint,
            lease_owner,
            "UNKNOWN_OUTCOME",
            conservative_charge=conservative_charge,
        )

    async def _finish(
        self,
        tenant_id: str,
        research_id: str,
        action_fingerprint: str,
        lease_owner: str,
        status: ResearchActionStatus,
        *,
        result: dict[str, object] | None = None,
        conservative_charge: dict[str, object] | None = None,
    ) -> ResearchAction:
        async with self.connection.transaction():
            await ensure_writes_enabled(self.connection, self.schema)
            row = await fetchone(
                self.connection,
                f"UPDATE {self.schema}.research_actions SET status=%s,result=%s,"
                "conservative_charge=%s,lease_owner=NULL,lease_expires_at=NULL,"
                "updated_at=clock_timestamp() "
                "WHERE tenant_id=%s AND research_id=%s AND action_fingerprint=%s "
                "AND status='IN_PROGRESS' AND lease_owner=%s "
                "RETURNING tenant_id,research_id,action_fingerprint,invocation_id,status,"
                "attempt,request,result,conservative_charge,lease_owner,lease_expires_at",
                (
                    status,
                    Jsonb(result) if result is not None else None,
                    Jsonb(conservative_charge)
                    if conservative_charge is not None
                    else None,
                    tenant_id,
                    research_id,
                    action_fingerprint,
                    lease_owner,
                ),
            )
            if row is None:
                existing = await self.get_action(
                    tenant_id, research_id, action_fingerprint
                )
                if existing is not None and existing.status == status:
                    return existing
                raise RuntimeError("RESEARCH_ACTION_LEASE_CONFLICT")
            return _action(row)

    async def get_action(
        self, tenant_id: str, research_id: str, action_fingerprint: str
    ) -> ResearchAction | None:
        row = await fetchone(
            self.connection,
            f"SELECT tenant_id,research_id,action_fingerprint,invocation_id,status,"
            "attempt,request,result,conservative_charge,lease_owner,lease_expires_at "
            f"FROM {self.schema}.research_actions "
            "WHERE tenant_id=%s AND research_id=%s AND action_fingerprint=%s",
            (tenant_id, research_id, action_fingerprint),
        )
        return None if row is None else _action(row)

    async def append_decision(
        self, tenant_id: str, research_id: str, payload: dict[str, object]
    ) -> int:
        async with self.connection.transaction():
            await ensure_writes_enabled(self.connection, self.schema)
            await self.connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"{tenant_id}:{research_id}",),
            )
            row = await fetchone(
                self.connection,
                f"INSERT INTO {self.schema}.research_decisions "
                "(tenant_id,research_id,decision_sequence,payload) "
                f"SELECT %s,%s,COALESCE(MAX(decision_sequence),0)+1,%s "
                f"FROM {self.schema}.research_decisions "
                "WHERE tenant_id=%s AND research_id=%s RETURNING decision_sequence",
                (tenant_id, research_id, Jsonb(payload), tenant_id, research_id),
            )
            assert row is not None
            return int(row[0])


def _action(row: tuple[Any, ...]) -> ResearchAction:
    return ResearchAction(
        tenant_id=str(row[0]),
        research_id=str(row[1]),
        action_fingerprint=str(row[2]),
        invocation_id=str(row[3]),
        status=row[4],
        attempt=int(row[5]),
        request=dict(row[6]),
        result=None if row[7] is None else dict(row[7]),
        conservative_charge=None if row[8] is None else dict(row[8]),
        lease_owner=None if row[9] is None else str(row[9]),
        lease_expires_at=row[10],
    )


def _identifiers(*values: str) -> None:
    if any(not value.strip() or len(value) > 256 for value in values):
        raise ValueError("动作标识必须是非空且有界字符串")


ResearchRepository = PostgresResearchRepository

__all__ = [
    "ActionClaim",
    "PostgresResearchRepository",
    "ResearchAction",
    "ResearchRepository",
]
