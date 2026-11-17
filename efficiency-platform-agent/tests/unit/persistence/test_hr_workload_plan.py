"""子scope不可重开批次累计额度，跨进程继续使用同一计划。"""

import pytest

from efficiency_platform_agent.core.paid_budget import (
    PaidBudgetError,
    PaidBudgetPlan,
    PaidPriceLimit,
    PaidWorkloadItem,
)
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger


def test_plan_aggregates_child_scopes_and_cannot_reset_on_reopen(tmp_path):
    path = tmp_path / "fake-only.db"
    ledger = SqlitePaidBudgetLedger(path)
    ledger.authorize(
        PaidBudgetPlan(
            "fixture",
            10,
            100,
            9999999999999,
            10,
            100,
            600000,
            4,
            1,
            10000,
            10000,
            0,
            10000,
            10000,
            0,
        ),
        (
            PaidPriceLimit(
                "p", "m", 100, 10, 5, "verified-fake", "v1", 100, 1000, 500, 1000
            ),
        ),
    )
    checked = ledger.check_workload(
        [
            PaidWorkloadItem("a", "p", "m", 1, 100, 100, 10),
            PaidWorkloadItem("b", "p", "m", 1, 100, 100, 10),
        ]
    )
    ref = checked["plan_ref"]
    for scope in ("a", "b"):
        reservation = ledger.reserve(
            None, scope, "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0
        )
        ledger.finish(reservation.reservation_id)
    reopened = SqlitePaidBudgetLedger(path)
    with pytest.raises(PaidBudgetError) as error:
        reopened.reserve(None, "a", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    assert error.value.code == "WORKLOAD_PLAN_EXHAUSTED"
    assert ledger.snapshot()["calls"] == 2
    with pytest.raises(PaidBudgetError):
        reopened.check_workload([], "fixture", ref)


def test_unknown_scope_cannot_use_an_existing_plan_reference(tmp_path):
    ledger = SqlitePaidBudgetLedger(tmp_path / "fake-only.db")
    ledger.authorize(
        PaidBudgetPlan(
            "fixture",
            10,
            100,
            9999999999999,
            10,
            100,
            600000,
            4,
            1,
            10000,
            10000,
            0,
            10000,
            10000,
            0,
        ),
        (
            PaidPriceLimit(
                "p", "m", 100, 10, 5, "verified-fake", "v1", 100, 1000, 500, 1000
            ),
        ),
    )
    ref = ledger.check_workload([PaidWorkloadItem("a", "p", "m", 1, 100, 100, 10)])[
        "plan_ref"
    ]
    with pytest.raises(PaidBudgetError) as error:
        ledger.check_workload_plan(ref, "unknown")
    assert error.value.code == "WORKLOAD_SCOPE_NOT_BOUND"
    assert ledger.snapshot()["calls"] == 0


def test_plan_releases_only_verified_usage_difference_and_keeps_call_count(tmp_path):
    from efficiency_platform_agent.core.paid_budget import PaidUsage

    ledger = SqlitePaidBudgetLedger(tmp_path / "fake-only.db")
    ledger.authorize(
        PaidBudgetPlan(
            "fixture",
            10,
            100,
            9999999999999,
            10,
            100,
            600000,
            4,
            1,
            10000,
            10000,
            0,
            10000,
            10000,
            0,
        ),
        (
            PaidPriceLimit(
                "p", "m", 100, 10, 5, "verified-fake", "v1", 100, 1000, 500, 1000
            ),
        ),
    )
    ref = ledger.check_workload([PaidWorkloadItem("a", "p", "m", 2, 100, 100, 10)])[
        "plan_ref"
    ]
    reservation = ledger.reserve(
        None, "a", "p", "m", 10, 1, input_tokens=10, reasoning_tokens=0
    )
    ledger.record_status(reservation.reservation_id, 200)
    ledger.settle(reservation.reservation_id, PaidUsage(1, 1))
    with ledger._db() as db:
        calls, cost = db.execute(
            "SELECT calls,cost FROM workload_plans WHERE id=?", (ref,)
        ).fetchone()
    assert calls == 1 and cost == 1
    ledger.finish(reservation.reservation_id)
    assert ledger.check_workload([], "fixture", ref)["plan_ref"] == ref


def test_existing_plan_scope_cannot_gain_a_second_expanded_allowance(tmp_path):
    ledger = SqlitePaidBudgetLedger(tmp_path / "fake-only.db")
    ledger.authorize(
        PaidBudgetPlan(
            "fixture",
            10,
            100,
            9999999999999,
            10,
            100,
            600000,
            4,
            1,
            10000,
            10000,
            0,
            10000,
            10000,
            0,
        ),
        (
            PaidPriceLimit(
                "p", "m", 100, 10, 5, "verified-fake", "v1", 100, 1000, 500, 1000
            ),
        ),
    )
    ledger.check_workload([PaidWorkloadItem("a", "p", "m", 1, 100, 100, 10)])
    with pytest.raises(PaidBudgetError) as error:
        ledger.check_workload([PaidWorkloadItem("a", "p", "m", 3, 100, 100, 10)])
    assert error.value.code == "WORKLOAD_PLAN_CONFLICT"


def test_explicit_manual_matching_scope_is_accepted_without_broadening_other_run_patterns():
    from pydantic import ValidationError

    from efficiency_platform_agent.contracts.hr import HrWorkload

    assert (
        HrWorkload(
            run_ref="hr-match-stable-business-hash",
            skill_key="hr.requirements.evaluate",
            attempts=1,
        ).attempts
        == 1
    )
    with pytest.raises(ValidationError):
        HrWorkload(run_ref="untrusted-arbitrary-scope", attempts=1)
