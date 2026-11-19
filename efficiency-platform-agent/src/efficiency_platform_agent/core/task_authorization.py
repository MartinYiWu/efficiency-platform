"""本机授权链合同；业务请求只提供已鉴权的执行身份，不创建费用授权。"""

from dataclasses import dataclass

from .memory import ExecutionScope, require_id
from .paid_budget import PaidBudgetError, _pos


@dataclass(frozen=True)
class TaskContinuation:
    task_id: str
    continuation_of: str
    max_total_cost_microunits: int
    max_total_http: int
    max_input_tokens: int
    max_output_tokens: int
    max_reasoning_tokens: int
    expires_at_epoch_ms: int

    def __post_init__(self) -> None:
        require_id(self.task_id)
        if not self.continuation_of or len(self.continuation_of) > 256:
            raise PaidBudgetError("INVALID_PLAN", "parent authorization required")
        for name in (
            "max_total_cost_microunits",
            "max_total_http",
            "max_input_tokens",
            "max_output_tokens",
            "max_reasoning_tokens",
            "expires_at_epoch_ms",
        ):
            _pos(
                getattr(self, name),
                name,
                name in {"max_output_tokens", "max_reasoning_tokens"},
            )
        if (
            self.max_total_http > 60
            or self.max_total_cost_microunits > 100_000_000
            or self.max_reasoning_tokens > self.max_output_tokens
        ):
            raise PaidBudgetError("TASK_LIMIT_EXPANSION", "task limits cannot increase")


@dataclass(frozen=True)
class TaskPaidBinding:
    scope: ExecutionScope
    operation_id: str
    input_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise PaidBudgetError(
                "TASK_SCOPE_REQUIRED", "trusted execution scope required"
            )
        require_id(self.operation_id)
        if not self.input_hash or len(self.input_hash) > 256:
            raise PaidBudgetError(
                "TASK_INPUT_REQUIRED", "frozen input identity required"
            )
