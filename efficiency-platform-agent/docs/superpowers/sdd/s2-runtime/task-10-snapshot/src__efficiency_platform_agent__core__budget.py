"""框架中立的执行预算账本与失败关闭守卫。"""

from __future__ import annotations

from dataclasses import dataclass

from .run import ExecutionBudget

_REASONS = {
    "iteration_limit",
    "tool_call_limit",
    "input_token_limit",
    "output_token_limit",
    "cost_limit",
    "absolute_timeout",
}


def _non_negative(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} 必须是非负整数")


def _positive(name: str, value: int) -> None:
    _non_negative(name, value)
    if value == 0:
        raise ValueError(f"{name} 必须为正整数")


@dataclass(frozen=True, slots=True)
class BudgetCharge:
    """一次节点、工具或模型尝试产生的可信消耗。"""

    iterations: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_microunits: int = 0

    def __post_init__(self) -> None:
        for name in ("iterations", "tool_calls", "input_tokens", "output_tokens", "cost_microunits"):
            _non_negative(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class BudgetState:
    """单个 Run 的绝对期限与累计消耗。"""

    consumed: BudgetCharge
    started_at_epoch_ms: int
    deadline_epoch_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.consumed, BudgetCharge):
            raise TypeError("consumed 必须是 BudgetCharge")
        _non_negative("started_at_epoch_ms", self.started_at_epoch_ms)
        _positive("deadline_epoch_ms", self.deadline_epoch_ms)
        if self.deadline_epoch_ms < self.started_at_epoch_ms:
            raise ValueError("deadline 不得早于开始时间")


@dataclass(frozen=True, slots=True)
class RemainingBudget:
    """当前时刻可继续执行的剩余额度。"""

    iterations: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    cost_microunits: int
    timeout_ms: int


class BudgetExhaustedError(RuntimeError):
    """预算任一维度不足时的稳定错误。"""

    code = "BUDGET_EXHAUSTED"

    def __init__(self, reason_code: str) -> None:
        if reason_code not in _REASONS:
            raise ValueError("未知预算耗尽原因")
        super().__init__("运行预算已耗尽")
        self.reason_code = reason_code


class BudgetGuard:
    """按绝对 deadline 与五维额度执行前后检查。"""

    def start(self, budget: ExecutionBudget, *, now_epoch_ms: int) -> BudgetState:
        """建立一次性预算状态，deadline 不随恢复重建。"""
        if not isinstance(budget, ExecutionBudget):
            raise TypeError("budget 必须是 ExecutionBudget")
        _non_negative("now_epoch_ms", now_epoch_ms)
        return BudgetState(
            consumed=BudgetCharge(),
            started_at_epoch_ms=now_epoch_ms,
            deadline_epoch_ms=now_epoch_ms + budget.timeout_ms,
        )

    def remaining(
        self,
        budget: ExecutionBudget,
        state: BudgetState,
        *,
        now_epoch_ms: int,
    ) -> RemainingBudget:
        """计算剩余量；超限或到达 deadline 立即失败。"""
        if not isinstance(budget, ExecutionBudget) or not isinstance(state, BudgetState):
            raise TypeError("budget/state 类型不正确")
        _non_negative("now_epoch_ms", now_epoch_ms)
        if now_epoch_ms >= state.deadline_epoch_ms:
            raise BudgetExhaustedError("absolute_timeout")
        consumed = state.consumed
        values = (
            ("iteration_limit", budget.max_iterations - consumed.iterations),
            ("tool_call_limit", budget.max_tool_calls - consumed.tool_calls),
            ("input_token_limit", budget.max_input_tokens - consumed.input_tokens),
            ("output_token_limit", budget.max_output_tokens - consumed.output_tokens),
            ("cost_limit", budget.max_cost_microunits - consumed.cost_microunits),
        )
        for reason, value in values:
            if value < 0:
                raise BudgetExhaustedError(reason)
        return RemainingBudget(
            iterations=values[0][1],
            tool_calls=values[1][1],
            input_tokens=values[2][1],
            output_tokens=values[3][1],
            cost_microunits=values[4][1],
            timeout_ms=state.deadline_epoch_ms - now_epoch_ms,
        )

    def check_before_node(
        self,
        budget: ExecutionBudget,
        state: BudgetState,
        required: BudgetCharge,
        *,
        now_epoch_ms: int,
    ) -> RemainingBudget:
        """在节点或尝试启动前预留最小额度。"""
        if not isinstance(required, BudgetCharge):
            raise TypeError("required 必须是 BudgetCharge")
        remaining = self.remaining(budget, state, now_epoch_ms=now_epoch_ms)
        for reason, need, available in (
            ("iteration_limit", required.iterations, remaining.iterations),
            ("tool_call_limit", required.tool_calls, remaining.tool_calls),
            ("input_token_limit", required.input_tokens, remaining.input_tokens),
            ("output_token_limit", required.output_tokens, remaining.output_tokens),
            ("cost_limit", required.cost_microunits, remaining.cost_microunits),
        ):
            if need > available:
                raise BudgetExhaustedError(reason)
        return remaining

    def record_after_node(
        self,
        budget: ExecutionBudget,
        state: BudgetState,
        actual: BudgetCharge,
        *,
        now_epoch_ms: int,
    ) -> tuple[BudgetState, RemainingBudget]:
        """记录可信实际消耗并再次检查，超限时不返回业务结果。"""
        if not isinstance(actual, BudgetCharge):
            raise TypeError("actual 必须是 BudgetCharge")
        self.remaining(budget, state, now_epoch_ms=now_epoch_ms)
        next_state = BudgetState(
            consumed=BudgetCharge(
                iterations=state.consumed.iterations + actual.iterations,
                tool_calls=state.consumed.tool_calls + actual.tool_calls,
                input_tokens=state.consumed.input_tokens + actual.input_tokens,
                output_tokens=state.consumed.output_tokens + actual.output_tokens,
                cost_microunits=state.consumed.cost_microunits + actual.cost_microunits,
            ),
            started_at_epoch_ms=state.started_at_epoch_ms,
            deadline_epoch_ms=state.deadline_epoch_ms,
        )
        return next_state, self.remaining(budget, next_state, now_epoch_ms=now_epoch_ms)
