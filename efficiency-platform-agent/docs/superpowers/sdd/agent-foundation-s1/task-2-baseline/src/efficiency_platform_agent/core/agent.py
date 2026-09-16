from __future__ import annotations

import re
from dataclasses import dataclass

from .enums import AgentKind, StrategyMode
from .run import ExecutionBudget


_STABLE_ID = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")
_SEMANTIC_VERSION = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


def _require_stable_id(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not _STABLE_ID.fullmatch(value):
        raise ValueError(f"{field_name} must be a stable lowercase identifier")


def _require_non_empty(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_string_set(
    field_name: str,
    value: frozenset[str],
    *,
    allow_empty: bool,
) -> None:
    if not isinstance(value, frozenset):
        raise TypeError(f"{field_name} must be a frozenset")
    if not allow_empty and not value:
        raise ValueError(f"{field_name} must not be empty")
    for item in value:
        _require_stable_id(field_name, item)


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    """可由 Registry 匹配的版本化能力声明。"""

    capability_id: str
    semantic_version: str
    owner: str
    input_schema_version: str
    output_schema_version: str
    permissions: frozenset[str]

    def __post_init__(self) -> None:
        _require_stable_id("capability_id", self.capability_id)
        if not _SEMANTIC_VERSION.fullmatch(self.semantic_version):
            raise ValueError("semantic_version must use MAJOR.MINOR.PATCH")
        _require_non_empty("owner", self.owner)
        _require_non_empty("input_schema_version", self.input_schema_version)
        _require_non_empty("output_schema_version", self.output_schema_version)
        _require_string_set("permissions", self.permissions, allow_empty=True)


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    """Supervisor 对 Specialist 能力的确定性匹配条件。"""

    all_of: frozenset[str] = frozenset()
    any_of: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _require_string_set("all_of", self.all_of, allow_empty=True)
        _require_string_set("any_of", self.any_of, allow_empty=True)
        if not self.all_of and not self.any_of:
            raise ValueError("at least one capability requirement must be present")


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Agent 注册、装配和治理所需的完整框架中立定义。"""

    agent_id: str
    semantic_version: str
    owner: str
    kind: AgentKind
    capability_ids: frozenset[str]
    supported_task_types: frozenset[str]
    input_schema_version: str
    output_schema_version: str
    state_schema_version: str
    checkpoint_version: str
    allowed_strategies: frozenset[StrategyMode]
    prompt_bundle_id: str
    allowed_tools: frozenset[str]
    knowledge_scopes: frozenset[str]
    memory_policy_id: str
    model_policy_id: str
    quality_policy_id: str
    permissions: frozenset[str]
    budget: ExecutionBudget
    termination_conditions: frozenset[str]

    def __post_init__(self) -> None:
        _require_stable_id("agent_id", self.agent_id)
        if not _SEMANTIC_VERSION.fullmatch(self.semantic_version):
            raise ValueError("semantic_version must use MAJOR.MINOR.PATCH")
        _require_non_empty("owner", self.owner)
        if not isinstance(self.kind, AgentKind):
            raise TypeError("kind must be an AgentKind")
        _require_string_set("capability_ids", self.capability_ids, allow_empty=False)
        _require_string_set("supported_task_types", self.supported_task_types, allow_empty=False)
        for field_name in (
            "input_schema_version",
            "output_schema_version",
            "state_schema_version",
            "checkpoint_version",
            "prompt_bundle_id",
            "memory_policy_id",
            "model_policy_id",
            "quality_policy_id",
        ):
            _require_non_empty(field_name, getattr(self, field_name))
        if not isinstance(self.allowed_strategies, frozenset):
            raise TypeError("allowed_strategies must be a frozenset")
        if not self.allowed_strategies:
            raise ValueError("allowed_strategies must not be empty")
        if any(not isinstance(strategy, StrategyMode) for strategy in self.allowed_strategies):
            raise TypeError("allowed_strategies must contain StrategyMode values")
        _require_string_set("allowed_tools", self.allowed_tools, allow_empty=True)
        _require_string_set("knowledge_scopes", self.knowledge_scopes, allow_empty=True)
        _require_string_set("permissions", self.permissions, allow_empty=True)
        if not isinstance(self.budget, ExecutionBudget):
            raise TypeError("budget must be an ExecutionBudget")
        _require_string_set("termination_conditions", self.termination_conditions, allow_empty=False)
