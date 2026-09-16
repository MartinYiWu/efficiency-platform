"""BudgetGuard 的五维额度与绝对截止时间契约测试。"""

from __future__ import annotations

import pytest

from efficiency_platform_agent.core.budget import (
    BudgetCharge,
    BudgetExhaustedError,
    BudgetGuard,
)
from efficiency_platform_agent.core.run import ExecutionBudget


def make_budget(**changes: int) -> ExecutionBudget:
    """构造默认合成预算。"""
    values = {
        "max_iterations": 3,
        "max_tool_calls": 2,
        "max_input_tokens": 10,
        "max_output_tokens": 8,
        "timeout_ms": 100,
        "max_cost_microunits": 20,
    }
    values.update(changes)
    return ExecutionBudget(**values)


def test_budget_guard_tracks_consumption_and_remaining_monotonically() -> None:
    """消费后各维度剩余量只减少，恢复使用原 deadline。"""
    guard = BudgetGuard()
    budget = make_budget()
    state = guard.start(budget, now_epoch_ms=1_000)
    assert state.deadline_epoch_ms == 1_100
    first = guard.remaining(budget, state, now_epoch_ms=1_010)
    next_state, second = guard.record_after_node(
        budget,
        state,
        BudgetCharge(iterations=1, input_tokens=2, output_tokens=3, cost_microunits=4),
        now_epoch_ms=1_020,
    )
    assert second.iterations < first.iterations
    assert second.input_tokens < first.input_tokens
    assert next_state.deadline_epoch_ms == state.deadline_epoch_ms
    assert guard.remaining(budget, next_state, now_epoch_ms=1_021).iterations == 2


@pytest.mark.parametrize(
    ("field", "charge_field", "reason"),
    [
        ("max_iterations", "iterations", "iteration_limit"),
        ("max_tool_calls", "tool_calls", "tool_call_limit"),
        ("max_input_tokens", "input_tokens", "input_token_limit"),
        ("max_output_tokens", "output_tokens", "output_token_limit"),
        ("max_cost_microunits", "cost_microunits", "cost_limit"),
    ],
)
def test_budget_guard_rejects_one_unit_over_limit(
    field: str, charge_field: str, reason: str
) -> None:
    """五类额度超过一单位时统一失败关闭。"""
    guard = BudgetGuard()
    budget = make_budget(**{field: 1})
    state = guard.start(budget, now_epoch_ms=1_000)
    required = BudgetCharge(**{charge_field: 2})

    with pytest.raises(BudgetExhaustedError) as error:
        guard.check_before_node(budget, state, required, now_epoch_ms=1_001)

    assert error.value.code == "BUDGET_EXHAUSTED"
    assert error.value.reason_code == reason


def test_budget_guard_rejects_absolute_deadline_at_exact_boundary() -> None:
    """now 等于 deadline 时不得再执行调用。"""
    guard = BudgetGuard()
    budget = make_budget(timeout_ms=10)
    state = guard.start(budget, now_epoch_ms=1_000)

    with pytest.raises(BudgetExhaustedError) as error:
        guard.remaining(budget, state, now_epoch_ms=1_010)

    assert error.value.reason_code == "absolute_timeout"


def test_budget_guard_rejects_negative_charge() -> None:
    """负消耗不能通过预算账本。"""
    with pytest.raises(ValueError):
        BudgetCharge(iterations=-1)
