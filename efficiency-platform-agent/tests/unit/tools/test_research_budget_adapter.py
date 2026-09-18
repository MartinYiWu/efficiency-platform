"""研究预算适配器只向父账本提交一次事实的测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.capabilities.research.v2.budget import (
    ResearchBudgetAdapter,
)
from efficiency_platform_agent.contracts.research_execution_v2 import (
    BudgetLeasePort as ContractBudgetLeasePort,
)
from efficiency_platform_agent.contracts.research_execution_v2 import (
    BudgetOutcomeV2,
    BudgetScopeV2,
    LedgerSnapshotV2,
)
from efficiency_platform_agent.core.budget_lease import (
    BudgetCharge,
    BudgetLimits,
    BudgetScope,
    InMemoryBudgetLeaseRepository,
    ReservationNotFoundError,
)
from efficiency_platform_agent.core.budget_lease import (
    BudgetLeasePort as CoreBudgetLeasePort,
)


@pytest.mark.asyncio
async def test_http_and_model_facts_share_parent_ledger_without_double_charge() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=3, max_bytes=2_000, max_cost_microunits=100)
    )
    adapter = ResearchBudgetAdapter(repository)
    scope = BudgetScope("tenant-1", "run-1", "research", "all")
    reservation = await adapter.reserve_http(scope, "http-1", expected_version=0, bytes=200)
    reservation = await adapter.mark_dispatched(reservation.reservation_id)
    snapshot = await adapter.settle_http(reservation.reservation_id, bytes=200, status="success")
    assert snapshot.used.calls == 1
    assert snapshot.used.bytes == 200

    model_reservation = await adapter.reserve_model(
        scope, "model-1", expected_version=snapshot.version, output_tokens=50
    )
    model_reservation = await adapter.mark_dispatched(model_reservation.reservation_id)
    final = await adapter.settle_model(
        model_reservation.reservation_id,
        input_tokens=20,
        output_tokens=50,
        cost_microunits=4,
        outcome="success",
    )
    assert final.used.calls == 2
    assert final.used.input_tokens == 20
    assert final.used.output_tokens == 50
    assert final.used.bytes == 200


@pytest.mark.asyncio
async def test_failed_or_cancelled_dispatch_never_spends_without_reservation() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=1, max_bytes=1_000, max_cost_microunits=0)
    )
    adapter = ResearchBudgetAdapter(repository)
    scope = BudgetScope("tenant-1", "run-1", "research", "http")
    with pytest.raises(ReservationNotFoundError):
        await adapter.settle_http("missing", bytes=1, status="cancelled")
    snapshot = await repository.snapshot(scope)
    assert snapshot.used == BudgetCharge()
    assert snapshot.reserved == BudgetCharge()


def test_execution_contract_matches_core_limits_and_single_port_truth() -> None:
    assert ContractBudgetLeasePort is CoreBudgetLeasePort
    source_account = "s" * 128
    scope_contract = BudgetScopeV2(
        tenant_id="tenant-1",
        run_id="run-1",
        stage="research",
        quota_dimension="http",
        source_account_id=source_account,
    )
    assert scope_contract.to_core().source_account_id == source_account
    with pytest.raises(ValidationError):
        BudgetScopeV2(
            tenant_id="tenant-1",
            run_id="run-1",
            stage="research",
            quota_dimension="http",
            source_account_id="s" * 129,
        )
    snapshot = LedgerSnapshotV2(
        scope=scope_contract,
        version=1,
        used={},
        reserved={},
        max_calls=2,
        max_bytes=1_000,
        max_cost_microunits=10,
        max_input_tokens=100,
        max_output_tokens=100,
        deadline_epoch_ms=2_000,
        output_token_reserve=25,
        output_time_reserve_ms=35_000,
    )
    assert snapshot.output_token_reserve == 25
    with pytest.raises(ValidationError):
        BudgetOutcomeV2(outcome="unknown", estimated=False, dispatch_confirmed=True)
