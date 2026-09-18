"""共享预算租约的并发与幂等行为测试。"""

from __future__ import annotations

import asyncio

import pytest

from efficiency_platform_agent.core.budget_lease import (
    BudgetCharge,
    BudgetExhaustedError,
    BudgetLimits,
    BudgetScope,
    InMemoryBudgetLeaseRepository,
    LeaseConflictError,
    ReservationNotFoundError,
)


def scope(*, tenant: str = "tenant-1", source: str | None = None) -> BudgetScope:
    return BudgetScope(
        tenant_id=tenant,
        run_id="run-1",
        stage="research",
        quota_dimension="http_calls",
        source_account_id=source,
    )


@pytest.mark.asyncio
async def test_concurrent_reservation_never_overspends() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=1, max_bytes=1_000, max_cost_microunits=0)
    )
    charge = BudgetCharge(calls=1, bytes=100)

    async def reserve(invocation_id: str):
        try:
            reservation = await repository.reserve(scope(), invocation_id, charge, 0)
            return await repository.mark_dispatched(reservation.reservation_id)
        except (BudgetExhaustedError, LeaseConflictError):
            return None

    first, second = await asyncio.gather(reserve("inv-1"), reserve("inv-2"))
    assert (first is None) != (second is None)
    assert repository.dispatched_invocation_count == 1
    snapshot = await repository.snapshot(scope())
    assert snapshot.reserved.calls == 1


@pytest.mark.asyncio
async def test_version_conflict_and_idempotent_settle() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=2, max_bytes=1_000, max_cost_microunits=100)
    )
    reservation = await repository.reserve(
        scope(), "inv-1", BudgetCharge(calls=1, cost_microunits=3), 0
    )
    with pytest.raises(LeaseConflictError):
        await repository.reserve(scope(), "inv-2", BudgetCharge(calls=1), 0)
    reservation = await repository.mark_dispatched(reservation.reservation_id)
    settled = await repository.settle(
        reservation.reservation_id, BudgetCharge(calls=1, cost_microunits=3), "success"
    )
    replay = await repository.settle(
        reservation.reservation_id, BudgetCharge(calls=1, cost_microunits=3), "success"
    )
    assert replay == settled
    assert settled.used.calls == 1
    assert settled.reserved.calls == 0


@pytest.mark.asyncio
async def test_unknown_outcome_keeps_conservative_charge_and_is_not_released() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=2, max_bytes=1_000, max_cost_microunits=100)
    )
    reservation = await repository.reserve(
        scope(), "inv-1", BudgetCharge(calls=1, cost_microunits=10), 0
    )
    reservation = await repository.mark_dispatched(reservation.reservation_id)
    snapshot = await repository.settle(
        reservation.reservation_id, BudgetCharge(unknown=True), "unknown"
    )
    assert snapshot.used.cost_microunits == 10
    assert snapshot.reserved.calls == 0
    with pytest.raises(ReservationNotFoundError):
        await repository.release(reservation.reservation_id)


@pytest.mark.asyncio
async def test_source_account_bucket_is_shared_but_tenant_run_usage_isolated() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=1, max_bytes=1_000, max_cost_microunits=0)
    )
    await repository.reserve(scope(tenant="tenant-1", source="shared-account"), "inv-1", BudgetCharge(calls=1), 0)
    with pytest.raises(BudgetExhaustedError):
        await repository.reserve(scope(tenant="tenant-2", source="shared-account"), "inv-2", BudgetCharge(calls=1), 1)
    other = await repository.reserve(scope(tenant="tenant-2", source="other-account"), "inv-3", BudgetCharge(calls=1), 0)
    assert other.scope.tenant_id == "tenant-2"


@pytest.mark.asyncio
async def test_shared_bucket_never_reuses_or_exposes_another_tenant_scope() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=2, max_bytes=1_000, max_cost_microunits=0)
    )
    first_scope = scope(tenant="tenant-1", source="shared-account")
    second_scope = scope(tenant="tenant-2", source="shared-account")
    first = await repository.reserve(first_scope, "same-invocation", BudgetCharge(calls=1), 0)
    second = await repository.reserve(second_scope, "same-invocation", BudgetCharge(calls=1), 1)
    assert first.reservation_id != second.reservation_id
    assert second.scope.tenant_id == "tenant-2"
    assert (await repository.snapshot(second_scope)).scope.tenant_id == "tenant-2"
    first_usage = await repository.usage_snapshot(first_scope)
    second_usage = await repository.usage_snapshot(second_scope)
    assert first_usage.reserved.calls == 1
    assert second_usage.reserved.calls == 1


@pytest.mark.asyncio
async def test_dispatched_reservation_cannot_be_released() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=1, max_bytes=1_000, max_cost_microunits=0)
    )
    reservation = await repository.reserve(scope(), "inv-1", BudgetCharge(calls=1), 0)
    await repository.mark_dispatched(reservation.reservation_id)
    with pytest.raises(ReservationNotFoundError):
        await repository.release(reservation.reservation_id)
    snapshot = await repository.snapshot(scope())
    assert snapshot.reserved.calls == 1


@pytest.mark.asyncio
async def test_settlement_keeps_other_reservations_inside_limit() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=3, max_bytes=1_000, max_cost_microunits=0)
    )
    first = await repository.reserve(scope(), "inv-1", BudgetCharge(calls=1), 0)
    await repository.reserve(scope(), "inv-2", BudgetCharge(calls=1), 1)
    first = await repository.mark_dispatched(first.reservation_id)
    settled = await repository.settle(
        first.reservation_id, BudgetCharge(calls=3), "success"
    )
    snapshot = await repository.snapshot(scope())
    assert settled.over_limit is True
    assert settled.delivery_allowed is False
    assert settled.used.calls == 3
    assert settled.reserved.calls == 1
    assert snapshot.used.calls == 3
    assert snapshot.reserved.calls == 1


@pytest.mark.asyncio
async def test_replay_is_idempotent_but_changed_settlement_conflicts() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=2, max_bytes=1_000, max_cost_microunits=10)
    )
    reservation = await repository.reserve(scope(), "inv-1", BudgetCharge(calls=1), 0)
    released = await repository.release(reservation.reservation_id)
    assert await repository.release(reservation.reservation_id) == released

    second = await repository.reserve(scope(), "inv-2", BudgetCharge(calls=1), released.version)
    second = await repository.mark_dispatched(second.reservation_id)
    actual = BudgetCharge(calls=1, cost_microunits=1)
    settled = await repository.settle(second.reservation_id, actual, "success")
    assert await repository.settle(second.reservation_id, actual, "success") == settled
    with pytest.raises(LeaseConflictError):
        await repository.settle(
            second.reservation_id,
            BudgetCharge(calls=1, cost_microunits=2),
            "success",
        )


@pytest.mark.asyncio
async def test_deadline_blocks_new_reserve_and_late_result_is_audit_only() -> None:
    now = 1_000
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=2,
            max_bytes=1_000,
            max_cost_microunits=0,
            deadline_epoch_ms=1_100,
        ),
        clock_ms=lambda: now,
    )
    reservation = await repository.reserve(scope(), "inv-1", BudgetCharge(calls=1), 0)
    reservation = await repository.mark_dispatched(reservation.reservation_id)
    now = 1_100
    await repository.settle(reservation.reservation_id, BudgetCharge(calls=1), "success")
    audit = repository.audit_records[-1]
    assert audit.late is True
    assert audit.delivery_allowed is False
    with pytest.raises(BudgetExhaustedError):
        await repository.reserve(scope(), "inv-2", BudgetCharge(calls=1), 2)


@pytest.mark.asyncio
async def test_cancelled_scope_makes_success_audit_only_before_deadline() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=1, max_bytes=1_000, max_cost_microunits=0)
    )
    active_scope = scope()
    reservation = await repository.reserve(
        active_scope, "inv-1", BudgetCharge(calls=1), 0
    )
    reservation = await repository.mark_dispatched(reservation.reservation_id)
    await repository.mark_scope_terminal(active_scope, "cancelled")
    settled = await repository.settle(
        reservation.reservation_id, BudgetCharge(calls=1), "success"
    )
    audit = repository.audit_records[-1]
    assert audit.late is True
    assert audit.delivery_allowed is False
    assert settled.settlement_late is True
    assert settled.delivery_allowed is False
    with pytest.raises(BudgetExhaustedError):
        await repository.reserve(
            active_scope, "after-cancel", BudgetCharge(calls=1), settled.version
        )


@pytest.mark.asyncio
async def test_terminal_between_reserve_and_dispatch_releases_reservation() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=1, max_bytes=1_000, max_cost_microunits=0)
    )
    active_scope = scope()
    reservation = await repository.reserve(
        active_scope, "inv-1", BudgetCharge(calls=1), 0
    )
    await repository.mark_scope_terminal(active_scope, "cancelled")
    with pytest.raises(BudgetExhaustedError):
        await repository.mark_dispatched(reservation.reservation_id)
    snapshot = await repository.snapshot(active_scope)
    assert snapshot.reserved.calls == 0
    assert repository.dispatched_invocation_count == 0


@pytest.mark.asyncio
async def test_deadline_between_reserve_and_dispatch_releases_reservation() -> None:
    now = 1_000
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=1,
            max_bytes=1_000,
            max_cost_microunits=0,
            deadline_epoch_ms=1_100,
        ),
        clock_ms=lambda: now,
    )
    active_scope = scope()
    reservation = await repository.reserve(
        active_scope, "inv-1", BudgetCharge(calls=1), 0
    )
    now = 1_100
    with pytest.raises(BudgetExhaustedError):
        await repository.mark_dispatched(reservation.reservation_id)
    snapshot = await repository.snapshot(active_scope)
    assert snapshot.reserved.calls == 0
    assert repository.dispatched_invocation_count == 0


@pytest.mark.asyncio
async def test_output_reserve_is_preserved_until_output_stage() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=2,
            max_bytes=1_000,
            max_cost_microunits=0,
            max_output_tokens=100,
            output_token_reserve=25,
        )
    )
    with pytest.raises(BudgetExhaustedError):
        await repository.reserve(
            scope(), "research-model", BudgetCharge(output_tokens=80), 0
        )
    output_scope = BudgetScope("tenant-1", "run-1", "output", "http_calls")
    reservation = await repository.reserve(
        output_scope, "final-output", BudgetCharge(output_tokens=80), 0
    )
    assert reservation.charge.output_tokens == 80
