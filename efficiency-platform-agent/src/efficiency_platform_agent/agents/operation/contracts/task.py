"""运营请求、任务和完整性值对象。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from efficiency_platform_agent.core.run import JsonObject, RunRequest

from .errors import OperationDomainError, OperationErrorCode, OperationErrorDetail

_ID = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")


def _id(name: str, value: str) -> None:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"{name} 必须是稳定小写标识")


def _text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 不能为空")


class OperationDomain(StrEnum):
    BRAND = "brand"
    IP = "ip"
    PRODUCT = "product"
    AUDIENCE = "audience"
    CONTENT = "content"
    CAMPAIGN = "campaign"
    CHANNEL = "channel"
    METRIC = "metric"


class OperationIntent(StrEnum):
    RESEARCH = "research"
    ANALYZE = "analyze"
    PLAN = "plan"
    CAMPAIGN = "campaign"
    CREATE = "create"
    REWRITE = "rewrite"
    ADAPT = "adapt"
    REVIEW = "review"
    OPTIMIZE = "optimize"


class OperationGoalKind(StrEnum):
    AWARENESS = "awareness"
    CONVERSION = "conversion"
    ENGAGEMENT = "engagement"
    GROWTH = "growth"
    EFFICIENCY = "efficiency"


class OperationObjectKind(StrEnum):
    BRAND = "brand"
    IP = "ip"
    PRODUCT = "product"
    CONTENT = "content"
    CAMPAIGN = "campaign"
    CHANNEL = "channel"


class SourceScope(StrEnum):
    USER_INPUT = "user_input"
    PROFILE = "profile"
    TOOL_RESULT = "tool_result"
    EXTERNAL_REFERENCE = "external_reference"


class ConditionImportance(StrEnum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    OPTIONAL = "optional"


class AssumptionStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class DeliverableKind(StrEnum):
    REPORT = "report"
    COPY = "copy"
    PLAN = "plan"
    ANALYSIS = "analysis"


@dataclass(frozen=True, slots=True)
class DeliverableRequirement:
    requirement_id: str
    kind: DeliverableKind
    quantity: int
    channel_ids: tuple[str, ...]
    format_id: str
    structure_id: str
    quality_check_ids: frozenset[str]

    def __post_init__(self) -> None:
        _id("requirement_id", self.requirement_id)
        if self.quantity < 1:
            raise ValueError("quantity 必须为正数")
        _text("format_id", self.format_id)
        _text("structure_id", self.structure_id)


@dataclass(frozen=True, slots=True)
class KeyCondition:
    condition_id: str
    label: str
    importance: ConditionImportance
    value: JsonObject | None

    def __post_init__(self) -> None:
        _id("condition_id", self.condition_id)
        _text("label", self.label)


@dataclass(frozen=True, slots=True)
class OperationAssumption:
    assumption_id: str
    condition_id: str
    value: JsonObject
    basis: str
    status: AssumptionStatus
    user_modifiable: bool

    def __post_init__(self) -> None:
        _id("assumption_id", self.assumption_id)
        _id("condition_id", self.condition_id)
        _text("basis", self.basis)
        if not self.user_modifiable:
            raise ValueError("运营假设必须允许用户修改")


@dataclass(frozen=True, slots=True)
class OperationGoal:
    goal_id: str
    kind: OperationGoalKind
    target_value: JsonObject | None
    description: str

    def __post_init__(self) -> None:
        _id("goal_id", self.goal_id)
        _text("description", self.description)


@dataclass(frozen=True, slots=True)
class OperationObject:
    object_id: str
    kind: OperationObjectKind
    description: str
    source_reference: str | None

    def __post_init__(self) -> None:
        _id("object_id", self.object_id)
        _text("description", self.description)


@dataclass(frozen=True, slots=True)
class OperationRequest:
    contract_version: str
    request: RunRequest
    operation_id: str
    session_id: str | None
    parent_task_id: str | None
    requested_domains: frozenset[OperationDomain]
    requested_deliverables: tuple[DeliverableRequirement, ...]

    def __post_init__(self) -> None:
        _text("contract_version", self.contract_version)
        _id("operation_id", self.operation_id)
        if self.session_id is not None:
            _id("session_id", self.session_id)
        if self.parent_task_id is not None:
            _id("parent_task_id", self.parent_task_id)

    def to_task_spec(
        self,
        *,
        task_id: str,
        tenant_id: str,
        user_id: str,
        intent: OperationIntent,
        domains: frozenset[OperationDomain],
        goals: tuple[OperationGoal, ...],
        objects: tuple[OperationObject, ...],
        key_conditions: tuple[KeyCondition, ...],
        assumptions: tuple[OperationAssumption, ...],
        source_scopes: frozenset[SourceScope],
        missing_critical_condition_ids: tuple[str, ...],
        requires_user_input: bool,
        requires_research: bool = False,
    ) -> OperationTaskSpec:
        if tenant_id != self.request.tenant_id or user_id != self.request.user_id:
            raise ValueError("任务身份与请求不一致")
        return OperationTaskSpec(
            "operation-task/1",
            task_id,
            tenant_id,
            user_id,
            self.session_id,
            self.parent_task_id,
            self.operation_id,
            intent,
            domains,
            goals,
            objects,
            key_conditions,
            assumptions,
            source_scopes,
            self.requested_deliverables,
            missing_critical_condition_ids,
            requires_user_input,
            requires_research,
        )


@dataclass(frozen=True, slots=True)
class OperationTaskSpec:
    contract_version: str
    task_id: str
    tenant_id: str
    user_id: str
    session_id: str | None
    parent_task_id: str | None
    operation_id: str
    intent: OperationIntent
    domains: frozenset[OperationDomain]
    goals: tuple[OperationGoal, ...]
    objects: tuple[OperationObject, ...]
    key_conditions: tuple[KeyCondition, ...]
    assumptions: tuple[OperationAssumption, ...]
    source_scopes: frozenset[SourceScope]
    deliverable_requirements: tuple[DeliverableRequirement, ...]
    missing_critical_condition_ids: tuple[str, ...]
    requires_user_input: bool
    requires_research: bool = False

    def __post_init__(self) -> None:
        for name, value in (
            ("task_id", self.task_id),
            ("operation_id", self.operation_id),
            ("tenant_id", self.tenant_id),
            ("user_id", self.user_id),
        ):
            _id(name, value)
        _text("contract_version", self.contract_version)
        if self.parent_task_id == self.task_id:
            raise ValueError("parent_task_id 不得等于 task_id")
        if self.session_id is not None:
            _id("session_id", self.session_id)
        if not isinstance(self.requires_user_input, bool):
            raise TypeError("requires_user_input 必须是布尔值")
        if not isinstance(self.requires_research, bool):
            raise TypeError("requires_research 必须是布尔值")


def validate_task_spec(task: OperationTaskSpec) -> None:
    """校验关键条件、假设与等待输入的一致性。"""
    if not isinstance(task, OperationTaskSpec):
        raise TypeError("task 必须是 OperationTaskSpec")
    condition_ids = {item.condition_id for item in task.key_conditions}
    critical = tuple(
        item.condition_id
        for item in task.key_conditions
        if item.importance is ConditionImportance.CRITICAL
    )
    missing = tuple(task.missing_critical_condition_ids)
    if task.requires_user_input != bool(missing):
        raise OperationDomainError(
            OperationErrorDetail(
                OperationErrorCode.OPERATION_INPUT_INCOMPLETE,
                "关键输入完整性与等待标志不一致",
                missing,
            )
        )
    if any(item not in condition_ids and item not in {"goal"} for item in missing):
        raise OperationDomainError(
            OperationErrorDetail(
                OperationErrorCode.OPERATION_INPUT_INCOMPLETE,
                "缺失条件未在任务中声明",
                missing,
            )
        )
    if any(item not in critical and item != "goal" for item in missing):
        raise OperationDomainError(
            OperationErrorDetail(
                OperationErrorCode.OPERATION_INPUT_INCOMPLETE,
                "非关键条件不得触发等待输入",
                missing,
            )
        )
    assumptions = {item.condition_id: item for item in task.assumptions}
    for condition in task.key_conditions:
        if (
            condition.importance is not ConditionImportance.CRITICAL
            and condition.value is None
            and condition.condition_id not in assumptions
        ):
            raise OperationDomainError(
                OperationErrorDetail(
                    OperationErrorCode.OPERATION_INPUT_INCOMPLETE,
                    "非关键缺失条件必须有可修改假设",
                    (condition.condition_id,),
                )
            )
    if (
        task.intent is OperationIntent.PLAN
        and OperationDomain.BRAND in task.domains
        and (
            not task.goals
            or not any(item.kind is OperationObjectKind.BRAND for item in task.objects)
            or not any(
                item.kind is OperationObjectKind.PRODUCT for item in task.objects
            )
        )
    ):
        raise OperationDomainError(
            OperationErrorDetail(
                OperationErrorCode.OPERATION_INPUT_INCOMPLETE,
                "品牌策略缺少品牌、产品或目标",
                ("brand", "goal"),
            )
        )


__all__ = [name for name in globals() if not name.startswith("_")]
