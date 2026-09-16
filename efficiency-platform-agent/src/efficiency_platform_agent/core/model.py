"""模型需求、候选和执行结果的框架中立契约。"""

from __future__ import annotations

from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from .budget import RemainingBudget
from .run import ProviderResult
from .runtime import UsageSnapshot


class ModelTier(StrEnum):
    """模型逻辑能力层级，只允许向更低费用层级降级。"""

    FAST = "fast"
    BALANCED = "balanced"
    STRONG = "strong"


def _text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")


def _non_negative(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} 必须是非负整数")


@dataclass(frozen=True, slots=True)
class ModelDemand:
    """Agent 对逻辑模型能力的版本化需求，不包含厂商或模型 ID。"""

    demand_version: str
    requested_tier: ModelTier
    requires_structured_output: bool
    requires_tools: bool
    estimated_input_tokens: int
    max_output_tokens: int

    def __post_init__(self) -> None:
        _text("demand_version", self.demand_version)
        if not isinstance(self.requested_tier, ModelTier):
            raise TypeError("requested_tier 必须是 ModelTier")
        if not isinstance(self.requires_structured_output, bool):
            raise TypeError("requires_structured_output 必须是 bool")
        if not isinstance(self.requires_tools, bool):
            raise TypeError("requires_tools 必须是 bool")
        _non_negative("estimated_input_tokens", self.estimated_input_tokens)
        _non_negative("max_output_tokens", self.max_output_tokens)


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    """候选模型能力描述；实际凭据不进入该契约。"""

    candidate_id: str
    provider_id: str
    logical_model: str
    tier: ModelTier
    supports_structured_output: bool
    supports_tools: bool
    max_context_tokens: int
    enabled: bool
    usage_is_estimated: bool

    def __post_init__(self) -> None:
        for text_name, text_value in (
            ("candidate_id", self.candidate_id),
            ("provider_id", self.provider_id),
            ("logical_model", self.logical_model),
        ):
            _text(text_name, text_value)
        if not isinstance(self.tier, ModelTier):
            raise TypeError("tier 必须是 ModelTier")
        for bool_name, bool_value in (
            ("supports_structured_output", self.supports_structured_output),
            ("supports_tools", self.supports_tools),
            ("enabled", self.enabled),
            ("usage_is_estimated", self.usage_is_estimated),
        ):
            if not isinstance(bool_value, bool):
                raise TypeError(f"{bool_name} 必须是 bool")
        _non_negative("max_context_tokens", self.max_context_tokens)


@dataclass(frozen=True, slots=True)
class ModelSelection:
    """一次模型候选尝试的可审计事实。"""

    candidate: ModelCandidate
    attempt: int
    degraded_from: ModelTier | None
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, ModelCandidate):
            raise TypeError("candidate 必须是 ModelCandidate")
        if (
            not isinstance(self.attempt, int)
            or isinstance(self.attempt, bool)
            or self.attempt < 1
        ):
            raise ValueError("attempt 必须是正整数")
        if self.degraded_from is not None and not isinstance(
            self.degraded_from, ModelTier
        ):
            raise TypeError("degraded_from 必须是 ModelTier 或 None")
        _text("reason_code", self.reason_code)


@dataclass(frozen=True, slots=True)
class ModelExecutionResult:
    """模型执行结果、全部尝试事实和可信用量。"""

    result: ProviderResult
    attempts: Sequence[ModelSelection]
    usage: UsageSnapshot
    degraded: bool

    def __post_init__(self) -> None:
        if not isinstance(self.result, ProviderResult):
            raise TypeError("result 必须是 ProviderResult")
        if not isinstance(self.attempts, tuple):
            object.__setattr__(self, "attempts", tuple(self.attempts))
        if any(not isinstance(item, ModelSelection) for item in self.attempts):
            raise TypeError("attempts 必须只包含 ModelSelection")
        if not isinstance(self.usage, UsageSnapshot):
            raise TypeError("usage 必须是 UsageSnapshot")
        if not isinstance(self.degraded, bool):
            raise TypeError("degraded 必须是 bool")


@runtime_checkable
class ModelCandidateSelector(Protocol):
    """Harness 注入的候选筛选端口。"""

    def candidates(
        self,
        demand: ModelDemand,
        *,
        remaining_budget: RemainingBudget,
        unavailable_candidate_ids: frozenset[str],
    ) -> Sequence[ModelCandidate]:
        """依据需求、预算和健康状态返回有序候选。"""
        ...


@runtime_checkable
class CancellationSignal(Protocol):
    """可选取消信号；实现可返回 bool 或异步 bool。"""

    def wait_requested(self) -> bool | Awaitable[bool]:
        """返回是否已请求取消。"""
        ...
