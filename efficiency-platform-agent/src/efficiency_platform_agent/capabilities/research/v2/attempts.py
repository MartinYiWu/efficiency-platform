"""研究来源尝试的租户/Run 隔离幂等账本端口。"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from efficiency_platform_agent.contracts.research_sources_v2 import SourceAttemptV2


class AttemptConflictError(RuntimeError):
    code = "SOURCE_ATTEMPT_CONFLICT"

    def __init__(self) -> None:
        super().__init__(self.code)


class InMemorySourceAttemptLedger:
    """离线实现；生产持久化与恢复由 X01 提供。"""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], dict[str, SourceAttemptV2]] = {}
        self._lock = asyncio.Lock()

    async def append(
        self, tenant_id: str, run_id: str, attempt: SourceAttemptV2
    ) -> None:
        await self.append_many(tenant_id, run_id, (attempt,))

    async def append_many(
        self,
        tenant_id: str,
        run_id: str,
        attempts: Iterable[SourceAttemptV2],
    ) -> None:
        _validate_scope(tenant_id, run_id)
        incoming = tuple(attempts)
        if any(not isinstance(item, SourceAttemptV2) for item in incoming):
            raise TypeError("attempts 必须是 SourceAttemptV2")
        incoming_by_id: dict[str, SourceAttemptV2] = {}
        for item in incoming:
            known = incoming_by_id.get(item.attempt_id)
            if known is not None and known != item:
                raise AttemptConflictError
            incoming_by_id[item.attempt_id] = item
        key = (tenant_id, run_id)
        async with self._lock:
            existing = self._records.get(key, {})
            for attempt_id, item in incoming_by_id.items():
                known = existing.get(attempt_id)
                if known is not None and known != item:
                    raise AttemptConflictError
            merged = dict(existing)
            merged.update(incoming_by_id)
            self._records[key] = merged

    async def list(
        self, tenant_id: str, run_id: str
    ) -> tuple[SourceAttemptV2, ...]:
        _validate_scope(tenant_id, run_id)
        async with self._lock:
            return tuple(self._records.get((tenant_id, run_id), {}).values())


def _validate_scope(tenant_id: str, run_id: str) -> None:
    if not tenant_id.strip() or not run_id.strip():
        raise ValueError("SOURCE_ATTEMPT_SCOPE_INVALID")


__all__ = ["AttemptConflictError", "InMemorySourceAttemptLedger"]
