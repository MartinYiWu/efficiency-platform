"""Run、事件和策略载荷的框架中立不可变事实。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from .budget import BudgetState
from .enums import RunStatus, StrategyMode
from .run import (
    ExecutionBudget,
    JsonObject,
    JsonValue,
    RunRequest,
    _validate_json_value,
    validate_run_status_transition,
)


def _required_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 不能为空")


def _non_negative(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} 必须是非负整数")


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    """模型与工具汇总的可信用量；Fake 运行必须显式标记 estimated。"""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_microunits: int = 0
    estimated: bool = False

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens", "cost_microunits"):
            _non_negative(name, getattr(self, name))
        if not isinstance(self.estimated, bool):
            raise TypeError("estimated 必须是 bool")


@dataclass(frozen=True, slots=True)
class StrategyPayload:
    """版本化且不可变的策略输入信封。"""

    schema_version: str
    data: JsonObject

    def __post_init__(self) -> None:
        _required_text("schema_version", self.schema_version)
        if not isinstance(self.data, JsonObject):
            raise TypeError("data 必须是 JsonObject")


@dataclass(frozen=True, slots=True)
class RunFailure:
    """不泄露内部细节的稳定运行错误。"""

    code: str
    category: str
    retryable: bool
    safe_message: str

    def __post_init__(self) -> None:
        _required_text("code", self.code)
        _required_text("category", self.category)
        if not isinstance(self.retryable, bool):
            raise TypeError("retryable 必须是 bool")
        if not isinstance(self.safe_message, str) or not 1 <= len(self.safe_message) <= 512:
            raise ValueError("safe_message 长度必须为 1 至 512")


@dataclass(frozen=True, slots=True)
class RunRecord:
    """单个 Run 的不可变权威内存快照。"""

    run_id: str
    request: RunRequest
    status: RunStatus
    strategy: StrategyMode | None
    budget: ExecutionBudget
    budget_state: BudgetState
    usage: UsageSnapshot
    version: int
    output: JsonValue = None
    failure: RunFailure | None = None
    checkpoint_id: str | None = None
    degraded: bool = False

    def __post_init__(self) -> None:
        _required_text("run_id", self.run_id)
        if not isinstance(self.request, RunRequest):
            raise TypeError("request 必须是 RunRequest")
        if not isinstance(self.status, RunStatus):
            raise TypeError("status 必须是 RunStatus")
        if self.strategy is not None and not isinstance(self.strategy, StrategyMode):
            raise TypeError("strategy 必须是 StrategyMode 或 None")
        if not isinstance(self.budget, ExecutionBudget):
            raise TypeError("budget 必须是 ExecutionBudget")
        if not isinstance(self.budget_state, BudgetState):
            raise TypeError("budget_state 必须是 BudgetState")
        if not isinstance(self.usage, UsageSnapshot):
            raise TypeError("usage 必须是 UsageSnapshot")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version 必须是正整数")
        _validate_json_value(self.output)
        if self.failure is not None and not isinstance(self.failure, RunFailure):
            raise TypeError("failure 必须是 RunFailure 或 None")
        if self.status is RunStatus.SUCCEEDED and (
            self.output is None or self.failure is not None
        ):
            raise ValueError("成功终态必须包含输出且不得包含失败")
        if self.status in {RunStatus.FAILED, RunStatus.TIMED_OUT} and (
            self.failure is None or self.output is not None
        ):
            raise ValueError("失败或超时终态必须包含错误且不得包含成功输出")
        if self.status not in {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.TIMED_OUT,
        } and (self.output is not None or self.failure is not None):
            raise ValueError("非终态不得携带最终输出或失败")
        if self.checkpoint_id is not None:
            _required_text("checkpoint_id", self.checkpoint_id)
        if not isinstance(self.degraded, bool):
            raise TypeError("degraded 必须是 bool")

    def transition(
        self,
        target: RunStatus,
        *,
        strategy: StrategyMode | None = None,
        output: JsonValue = None,
        failure: RunFailure | None = None,
        checkpoint_id: str | None = None,
        usage: UsageSnapshot | None = None,
        budget_state: BudgetState | None = None,
        degraded: bool | None = None,
    ) -> RunRecord:
        """执行状态机校验并生成版本递增的新快照。"""
        if target is self.status:
            return self
        validate_run_status_transition(self.status, target)
        if target is RunStatus.SUCCEEDED and (output is None or failure is not None):
            raise ValueError("成功终态必须包含输出且不得包含失败")
        if target in {RunStatus.FAILED, RunStatus.TIMED_OUT} and (failure is None or output is not None):
            raise ValueError("失败或超时终态必须包含错误且不得包含成功输出")
        if target not in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.TIMED_OUT} and (output is not None or failure is not None):
            raise ValueError("非终态不得携带最终输出或失败")
        next_budget = self.budget_state if budget_state is None else budget_state
        if next_budget.started_at_epoch_ms != self.budget_state.started_at_epoch_ms or next_budget.deadline_epoch_ms != self.budget_state.deadline_epoch_ms:
            raise ValueError("预算开始时间和 deadline 不可改写")
        old = self.budget_state.consumed
        new = next_budget.consumed
        for name in ("iterations", "tool_calls", "input_tokens", "output_tokens", "cost_microunits"):
            if getattr(new, name) < getattr(old, name):
                raise ValueError("预算消费不得倒退")
        return replace(
            self,
            status=target,
            strategy=self.strategy if strategy is None else strategy,
            output=output,
            failure=failure,
            checkpoint_id=self.checkpoint_id if checkpoint_id is None else checkpoint_id,
            usage=self.usage if usage is None else usage,
            budget_state=next_budget,
            degraded=self.degraded if degraded is None else degraded,
            version=self.version + 1,
        )


_EVENT_TYPES = frozenset(
    {
        "run_created", "run_queued", "run_started", "strategy_selected", "context_built",
        "prompt_rendered", "tool_started", "tool_completed", "model_selected", "model_degraded",
        "model_completed", "checkpoint_saved", "budget_exhausted", "strategy_event",
        "run_waiting_input", "run_resumed", "run_cancel_requested", "run_cancelled",
        "run_timed_out", "run_succeeded", "run_failed",
    }
)
_STRATEGY_EVENT_KEYS = frozenset(
    {"strategy_event_type", "graph_id", "plan_id", "task_id", "attempt", "revision", "fence_token", "reason_code", "counts", "usage_delta"}
)
_SENSITIVE_EVENT_KEYS = frozenset({"input_text", "rendered_prompt", "prompt", "arguments", "exception", "secret", "provider_script"})


@dataclass(frozen=True, slots=True)
class RunEventRecord:
    """可回放的不可变运行事件事实。"""

    event_id: str
    event_type: str
    run_id: str
    tenant_id: str
    sequence: int
    occurred_at_epoch_ms: int
    status: RunStatus
    payload: JsonObject = field(default_factory=JsonObject)

    def __post_init__(self) -> None:
        for text_name, text_value in (
            ("event_id", self.event_id),
            ("event_type", self.event_type),
            ("run_id", self.run_id),
            ("tenant_id", self.tenant_id),
        ):
            _required_text(text_name, text_value)
        if self.event_type not in _EVENT_TYPES:
            raise ValueError("未知事件类型")
        for numeric_name, numeric_value in (
            ("sequence", self.sequence),
            ("occurred_at_epoch_ms", self.occurred_at_epoch_ms),
        ):
            if (
                not isinstance(numeric_value, int)
                or isinstance(numeric_value, bool)
                or numeric_value < 1
            ):
                raise ValueError(f"{numeric_name} 必须是正整数")
        if not isinstance(self.status, RunStatus):
            raise TypeError("status 必须是 RunStatus")
        if not isinstance(self.payload, JsonObject):
            raise TypeError("payload 必须是 JsonObject")
        _validate_event_payload(self.payload, strategy_event=self.event_type == "strategy_event")


@dataclass(frozen=True, slots=True)
class ExecutionFact:
    """供运行时审计的结构化事实。"""

    fact_type: str
    payload: JsonObject = field(default_factory=JsonObject)

    def __post_init__(self) -> None:
        _required_text("fact_type", self.fact_type)
        if not isinstance(self.payload, JsonObject):
            raise TypeError("payload 必须是 JsonObject")


def _validate_event_payload(value: object, *, strategy_event: bool, allow_nested_keys: bool = False) -> None:
    """递归校验事件 payload 的敏感键和 strategy_event 信封白名单。"""
    if isinstance(value, JsonObject):
        for key, item in value.items:
            if key in _SENSITIVE_EVENT_KEYS:
                raise ValueError("事件 payload 不得包含敏感正文")
            if strategy_event and not allow_nested_keys and key not in _STRATEGY_EVENT_KEYS:
                raise ValueError("strategy_event payload 存在未声明字段")
            child_allows_arbitrary = allow_nested_keys or key in {"counts", "usage_delta"}
            _validate_event_payload(
                item,
                strategy_event=strategy_event,
                allow_nested_keys=child_allows_arbitrary,
            )
        return
    if isinstance(value, tuple):
        for item in value:
            _validate_event_payload(
                item,
                strategy_event=strategy_event,
                allow_nested_keys=allow_nested_keys,
            )
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key in _SENSITIVE_EVENT_KEYS:
                raise ValueError("事件 payload 不得包含敏感正文")
            _validate_event_payload(
                item,
                strategy_event=strategy_event,
                allow_nested_keys=allow_nested_keys,
            )
