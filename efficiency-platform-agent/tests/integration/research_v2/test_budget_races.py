"""X01 PostgreSQL 预算租约并发竞态。"""

from __future__ import annotations

import asyncio

from efficiency_platform_agent.core.budget_lease import (
    BudgetCharge,
    BudgetLimits,
    BudgetScope,
    LeaseConflictError,
)
from efficiency_platform_agent.persistence.research_budget import (
    PostgresBudgetLeaseRepository,
)


async def test_two_connections_cannot_over_reserve_same_budget(x01_connections) -> None:
    first, second = x01_connections
    limits = BudgetLimits(max_calls=1, max_bytes=100, max_cost_microunits=0)
    repo_a = PostgresBudgetLeaseRepository(first, "agent_runtime", limits)
    repo_b = PostgresBudgetLeaseRepository(second, "agent_runtime", limits)
    scope = BudgetScope("tenant-race", "run-race", "research", "http")

    results = await asyncio.gather(
        repo_a.reserve(scope, "invocation-a", BudgetCharge(calls=1), 0),
        repo_b.reserve(scope, "invocation-b", BudgetCharge(calls=1), 0),
        return_exceptions=True,
    )
    assert sum(not isinstance(item, Exception) for item in results) == 1
    assert sum(isinstance(item, LeaseConflictError) for item in results) == 1


async def test_unknown_settlement_keeps_conservative_charge(x01_connections) -> None:
    first, _ = x01_connections
    limits = BudgetLimits(max_calls=2, max_bytes=100, max_cost_microunits=0)
    repo = PostgresBudgetLeaseRepository(first, "agent_runtime", limits)
    scope = BudgetScope("tenant-unknown", "run-unknown", "research", "http")
    reservation = await repo.reserve(
        scope, "invocation-unknown", BudgetCharge(calls=1), 0
    )
    await repo.mark_dispatched(reservation.reservation_id)
    snapshot = await repo.settle(
        reservation.reservation_id, BudgetCharge(unknown=True), "unknown"
    )
    assert snapshot.used.calls == 1
    assert snapshot.used.unknown is True
    assert snapshot.delivery_allowed is False
