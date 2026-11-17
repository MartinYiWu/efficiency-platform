import pytest

from efficiency_platform_agent.core.paid_budget import (
    PaidBudgetError,
    PaidBudgetPlan,
    current_paid_scope,
    paid_scope,
)


def test_plan_and_scope():
    p = PaidBudgetPlan("b", 1, 10, 1000, 1, 10, 100, 2, 1)
    assert p.budget_id == "b"
    with paid_scope("x"):
        assert current_paid_scope() == "x"
    assert current_paid_scope() == "unscoped"


def test_invalid_plan():
    with pytest.raises(PaidBudgetError):
        PaidBudgetPlan("b", True, 1, 1, 1, 1, 1, 1, 1)


def test_scope_restores_after_exception():
    with pytest.raises(ValueError), paid_scope("outer"):
        raise ValueError()
    assert current_paid_scope() == "unscoped"


@pytest.mark.parametrize("bad", [True, -1, 1.0, 2**64])
def test_plan_integer_boundary(bad):
    with pytest.raises(PaidBudgetError):
        PaidBudgetPlan("b", bad, 10, 1000, 1, 10, 100, 2, 1)


from efficiency_platform_agent.core.paid_budget import (
    PaidPriceLimit,
    PaidUsage,
    calculate_paid_cost,
)


def test_cost_integer_ceil_cache_and_reasoning_subsets():
    price = PaidPriceLimit("p", "m", 100, 10, 100, "manual", "v1", 100, 3, 1, 5)
    assert calculate_paid_cost(PaidUsage(1000000, 1000000, 500000, 800000), price) == 7
    assert calculate_paid_cost(PaidUsage(1, 1), price) == 1
    assert calculate_paid_cost(PaidUsage(0, 0), price) == 0


@pytest.mark.parametrize(
    "args",
    [(1, 0, 2, 0), (1, 1, 0, 2), (True, 0, 0, 0), (-1, 0, 0, 0), (0, 2**63, 0, 0)],
)
def test_usage_invalid(args):
    with pytest.raises(PaidBudgetError):
        PaidUsage(*args)
