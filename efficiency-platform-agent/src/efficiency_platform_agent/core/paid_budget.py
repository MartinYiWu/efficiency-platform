from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .task_authorization import TaskPaidBinding


class PaidBudgetError(RuntimeError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


def _pos(v: int, name: str, zero: bool = False) -> int:
    if (
        isinstance(v, bool)
        or not isinstance(v, int)
        or (v < 0 if zero else v <= 0)
        or v > 2**63 - 1
    ):
        raise PaidBudgetError("INVALID_PLAN", f"invalid {name}")
    return v


@dataclass(frozen=True)
class PaidBudgetPlan:
    budget_id: str
    max_calls: int
    max_cost_microunits: int
    deadline_epoch_ms: int
    max_run_calls: int
    max_run_cost_microunits: int
    max_run_duration_ms: int
    max_inflight: int
    max_429_responses: int
    max_input_tokens: int = 0
    max_output_tokens: int = 0
    max_reasoning_tokens: int = 0
    max_run_input_tokens: int = 0
    max_run_output_tokens: int = 0
    max_run_reasoning_tokens: int = 0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.budget_id, str)
            or not self.budget_id.strip()
            or len(self.budget_id) > 256
        ):
            raise PaidBudgetError("INVALID_PLAN", "budget id required")
        for n in (
            "max_calls",
            "max_cost_microunits",
            "deadline_epoch_ms",
            "max_run_calls",
            "max_run_cost_microunits",
            "max_run_duration_ms",
            "max_inflight",
            "max_429_responses",
            "max_input_tokens",
            "max_output_tokens",
            "max_reasoning_tokens",
            "max_run_input_tokens",
            "max_run_output_tokens",
            "max_run_reasoning_tokens",
        ):
            _pos(getattr(self, n), n, True)


@dataclass(frozen=True)
class PaidPriceLimit:
    provider: str
    model: str
    max_request_bytes: int
    max_output_tokens: int
    max_cost_microunits_per_attempt: int
    pricing_source: str
    pricing_version: str = ""
    max_input_tokens: int = 0
    input_microunits_per_million: int = 0
    cached_input_microunits_per_million: int = 0
    output_microunits_per_million: int = 0

    def __post_init__(self) -> None:
        if any(
            not isinstance(v, str) or not v.strip() or len(v) > 1024
            for v in (self.provider, self.model, self.pricing_source)
        ):
            raise PaidBudgetError("INVALID_PRICE", "missing price identity")
        _pos(self.max_request_bytes, "request")
        _pos(self.max_output_tokens, "output", True)
        _pos(self.max_cost_microunits_per_attempt, "cost")
        if not isinstance(self.pricing_version, str) or len(self.pricing_version) > 256:
            raise PaidBudgetError("INVALID_PRICE", "invalid price version")
        for name in (
            "max_input_tokens",
            "input_microunits_per_million",
            "cached_input_microunits_per_million",
            "output_microunits_per_million",
        ):
            _pos(getattr(self, name), name, True)


@dataclass(frozen=True)
class PaidUsage:
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    reasoning_tokens: int = 0

    def __post_init__(self) -> None:
        for name in (
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "reasoning_tokens",
        ):
            _pos(getattr(self, name), name, True)
        if (
            self.cached_tokens > self.input_tokens
            or self.reasoning_tokens > self.output_tokens
        ):
            raise PaidBudgetError("INVALID_USAGE", "token subsets exceed totals")


def calculate_paid_cost(usage: PaidUsage, price: PaidPriceLimit) -> int:
    # 缓存属于输入，推理属于输出，合计一次向上取整，不能重复计费。
    numerator = (
        (usage.input_tokens - usage.cached_tokens) * price.input_microunits_per_million
        + usage.cached_tokens * price.cached_input_microunits_per_million
        + usage.output_tokens * price.output_microunits_per_million
    )
    return _pos((numerator + 999_999) // 1_000_000, "calculated_cost", True)


@dataclass(frozen=True)
class PaidWorkloadItem:
    """服务器已绑定供应商/模型的单逻辑操作最坏工作量；不代表预算授权。"""

    scope_id: str
    provider: str
    model: str
    attempts: int
    request_bytes: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int = 0

    def __post_init__(self) -> None:
        if (
            not self.scope_id
            or len(self.scope_id) > 200
            or not self.provider
            or not self.model
        ):
            raise PaidBudgetError("INVALID_WORKLOAD", "invalid workload identity")
        for name in (
            "attempts",
            "request_bytes",
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
        ):
            _pos(getattr(self, name), name, name == "reasoning_tokens")
        if self.attempts > 3 or self.reasoning_tokens > self.output_tokens:
            raise PaidBudgetError("INVALID_WORKLOAD", "invalid operation bounds")


@dataclass(frozen=True)
class PaidReservation:
    reservation_id: str
    deadline_epoch_ms: int


class PaidBudgetLedger(Protocol):
    @property
    def task_authorization_enabled(self) -> bool: ...
    def task_budget_id(
        self, binding: TaskPaidBinding, fallback: str | None
    ) -> str | None: ...
    def authorize(
        self, plan: PaidBudgetPlan, prices: tuple[PaidPriceLimit, ...]
    ) -> None: ...
    def active_budget_id(self) -> str | None: ...
    def reserve(
        self,
        budget_id: str | None,
        scope_id: str,
        provider: str,
        model: str,
        request_bytes: int,
        output_tokens: int,
        *,
        input_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        task_binding: TaskPaidBinding | None = None,
    ) -> PaidReservation: ...
    def settle(self, reservation_id: str, usage: PaidUsage) -> None: ...
    def finish(self, reservation_id: str) -> None: ...
    def check_live(self, reservation_id: str) -> None: ...
    def record_status(self, reservation_id: str, status: int) -> None: ...
    def stop(self, budget_id: str, reason: str) -> None: ...
    def snapshot(self, budget_id: str | None = None) -> dict[str, object]: ...
    def details(self, budget_id: str | None = None) -> dict[str, object]: ...


_scope = ContextVar("paid_scope", default="unscoped")


@contextmanager
def paid_scope(scope_id: str) -> Iterator[str]:
    t = _scope.set(scope_id)
    try:
        yield scope_id
    finally:
        _scope.reset(t)


def current_paid_scope() -> str:
    return _scope.get()
