"""整批预检只核实统一总账，不发送HTTP、授权或清空旧占用。"""

from dataclasses import replace

import pytest

from efficiency_platform_agent.core.paid_budget import (
    PaidBudgetError,
    PaidBudgetPlan,
    PaidPriceLimit,
    PaidWorkloadItem,
)
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger


def plan():
    return PaidBudgetPlan(
        "fixture",
        6,
        60,
        9999999999999,
        6,
        60,
        600000,
        1,
        1,
        10000,
        10000,
        0,
        10000,
        10000,
        0,
    )


def price():
    return PaidPriceLimit(
        "p", "m", 100, 10, 10, "verified-fake", "v1", 100, 1000, 500, 1000
    )


def test_preflight_rejects_whole_workload_without_spending_and_keeps_stopped_state(
    tmp_path,
):
    ledger = SqlitePaidBudgetLedger(tmp_path / "fake-only.db")
    work = [PaidWorkloadItem("s", "p", "m", 3, 100, 100, 10, 0)]
    with pytest.raises(PaidBudgetError, match="budget"):
        ledger.check_workload(work)
    ledger.authorize(plan(), (price(),))
    assert ledger.check_workload(work)["maximum_calls"] == 3
    assert ledger.snapshot()["calls"] == 0
    with pytest.raises(PaidBudgetError) as error:
        ledger.check_workload(work * 3)
    assert error.value.code == "BUDGET_EXHAUSTED"
    assert ledger.snapshot()["calls"] == 0
    ledger.stop("fixture", "manual")
    with pytest.raises(PaidBudgetError) as error:
        ledger.check_workload(work)
    assert error.value.code == "BUDGET_STOPPED"


def test_preflight_checks_frozen_prices_scope_attempts_tokens_and_current_occupancy(
    tmp_path,
):
    ledger = SqlitePaidBudgetLedger(tmp_path / "fake-only.db")
    ledger.authorize(replace(plan(), max_calls=3), (price(),))
    ledger.reserve(None, "existing", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    with pytest.raises(PaidBudgetError):
        ledger.check_workload([PaidWorkloadItem("new", "p", "m", 3, 100, 100, 10, 0)])
    with pytest.raises(PaidBudgetError):
        ledger.check_workload(
            [PaidWorkloadItem("new", "unknown", "m", 1, 100, 100, 10, 0)]
        )
    assert ledger.snapshot()["calls"] == 1


def test_frozen_budget_reference_cannot_switch_to_new_authorization(tmp_path):
    ledger = SqlitePaidBudgetLedger(tmp_path / "fake-only.db")
    ledger.authorize(plan(), (price(),))
    work = [PaidWorkloadItem("s", "p", "m", 1, 100, 100, 10, 0)]
    assert ledger.check_workload(work)["budget_ref"] == "fixture"
    ledger.authorize(replace(plan(), budget_id="new-fixture"), (price(),))
    with pytest.raises(PaidBudgetError) as error:
        ledger.check_workload(work, "fixture")
    assert error.value.code == "BUDGET_REFERENCE_CHANGED"
    assert ledger.snapshot()["calls"] == 0
