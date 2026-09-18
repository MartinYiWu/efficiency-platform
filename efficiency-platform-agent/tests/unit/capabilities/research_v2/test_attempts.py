"""研究来源执行账本的租户隔离与幂等测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from efficiency_platform_agent.capabilities.research.v2.attempts import (
    AttemptConflictError,
    InMemorySourceAttemptLedger,
)
from efficiency_platform_agent.contracts.research_sources_v2 import (
    SourceAttemptV2,
    SourceUsageV2,
)


def _attempt(attempt_id: str, *, returned: int = 1) -> SourceAttemptV2:
    return SourceAttemptV2(
        attempt_id=attempt_id,
        action_id="action-1",
        source_id="source-1",
        status="success" if returned else "success_empty",
        started_at=datetime(2026, 9, 16, tzinfo=UTC),
        finished_at=datetime(2026, 9, 16, 0, 0, 1, tzinfo=UTC),
        returned_count=returned,
        filtered_count=0,
        coverage="complete",
        lease_id="lease-1",
        usage=SourceUsageV2(
            requests=1,
            returned_items=returned,
            downloaded_bytes=10,
        ),
    )


@pytest.mark.asyncio
async def test_attempts_are_isolated_by_tenant_and_run() -> None:
    ledger = InMemorySourceAttemptLedger()
    await ledger.append("tenant-1", "run-1", _attempt("attempt-1"))
    await ledger.append("tenant-1", "run-2", _attempt("attempt-1"))
    await ledger.append("tenant-2", "run-1", _attempt("attempt-1"))

    assert len(await ledger.list("tenant-1", "run-1")) == 1
    assert len(await ledger.list("tenant-1", "run-2")) == 1
    assert len(await ledger.list("tenant-2", "run-1")) == 1
    assert await ledger.list("tenant-2", "run-2") == ()


@pytest.mark.asyncio
async def test_identical_append_is_idempotent_but_conflict_fails() -> None:
    ledger = InMemorySourceAttemptLedger()
    attempt = _attempt("attempt-1")
    await ledger.append("tenant-1", "run-1", attempt)
    await ledger.append("tenant-1", "run-1", attempt)

    assert await ledger.list("tenant-1", "run-1") == (attempt,)
    with pytest.raises(AttemptConflictError, match="SOURCE_ATTEMPT_CONFLICT"):
        await ledger.append(
            "tenant-1", "run-1", _attempt("attempt-1", returned=2)
        )


@pytest.mark.asyncio
async def test_batch_append_is_atomic_on_conflict() -> None:
    ledger = InMemorySourceAttemptLedger()
    await ledger.append("tenant-1", "run-1", _attempt("attempt-1"))

    with pytest.raises(AttemptConflictError):
        await ledger.append_many(
            "tenant-1",
            "run-1",
            (_attempt("attempt-2"), _attempt("attempt-1", returned=2)),
        )

    assert [item.attempt_id for item in await ledger.list("tenant-1", "run-1")] == [
        "attempt-1"
    ]
