"""运营场景包的声明性模板、清单和确定性编译契约。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from efficiency_platform_agent.core.agent import CapabilityRequirement
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.run import ExecutionBudget

from .planning import (
    FailureBehavior,
    OperationPlan,
    OperationPlanStep,
    validate_operation_plan,
)
from .profiles import OperationContext, ProfileKind
from .task import (
    DeliverableRequirement,
    KeyCondition,
    OperationAssumption,
    OperationIntent,
    OperationTaskSpec,
)

_STABLE_ID = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")
_QUALITY_CHECK_ID = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?/[1-9][0-9]*")
_SEMANTIC_VERSION = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
_PLATFORM_ALIASES = {
    "xiaohongshu": "xiaohongshu",
    "小红书": "xiaohongshu",
    "wechat_official_account": "wechat_official_account",
    "wechat-official-account": "wechat_official_account",
    "wechat": "wechat_official_account",
    "微信公众号": "wechat_official_account",
    "公众号": "wechat_official_account",
    "toutiao": "toutiao",
    "今日头条": "toutiao",
    "头条": "toutiao",
}


class ClarificationPolicy(StrEnum):
    """场景缺少关键条件时的声明性处理策略。"""

    ASK_USER = "ask_user"
    USE_DEFAULTS = "use_defaults"
    ASK_IF_REQUIRED_MISSING = "ask_if_required_missing"
    REQUIRE_INPUT = "ask_user"
    USE_DEFAULT = "use_defaults"


def _stable_id(name: str, value: str) -> None:
    if not isinstance(value, str) or _STABLE_ID.fullmatch(value) is None:
        raise ValueError(f"{name}必须是稳定的小写标识")


def _text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}不能为空")


def _semantic_version(name: str, value: str) -> None:
    if not isinstance(value, str) or _SEMANTIC_VERSION.fullmatch(value) is None:
        raise ValueError(f"{name}必须使用MAJOR.MINOR.PATCH")


def _string_tuple(name: str, values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{name}必须是不可变元组")
    if len(set(values)) != len(values):
        raise ValueError(f"{name}不能重复")
    for value in values:
        _stable_id(name, value)


def _string_set(name: str, values: frozenset[str]) -> None:
    if not isinstance(values, frozenset):
        raise TypeError(f"{name}必须是不可变集合")
    for value in values:
        _stable_id(name, value)


def _quality_check_set(values: frozenset[str]) -> None:
    """校验带主版本后缀的质量检查标识。"""

    if not isinstance(values, frozenset):
        raise TypeError("quality_check_ids必须是不可变集合")
    for value in values:
        if not isinstance(value, str) or (
            _STABLE_ID.fullmatch(value) is None
            and _QUALITY_CHECK_ID.fullmatch(value) is None
        ):
            raise ValueError("quality_check_ids必须是稳定标识/主版本格式")


@dataclass(frozen=True, slots=True)
class ScenarioStepDefinition:
    """一个只声明选择元数据和依赖关系的场景模板步骤。"""

    contract_version: str
    semantic_version: str
    step_id: str
    task_type: str
    depends_on_step_ids: tuple[str, ...]
    required_capabilities: CapabilityRequirement
    input_schema_version: str
    output_schema_version: str
    input_reference_ids: tuple[str, ...]
    allowed_tools: frozenset[str]
    required_permissions: frozenset[str]
    budget: ExecutionBudget
    expected_deliverable_ids: tuple[str, ...]
    quality_check_ids: frozenset[str]
    required: bool
    failure_behavior: FailureBehavior

    def __post_init__(self) -> None:
        if self.contract_version != "scenario-step/1":
            raise ValueError("contract_version必须为scenario-step/1")
        _semantic_version("semantic_version", self.semantic_version)
        _stable_id("step_id", self.step_id)
        _stable_id("task_type", self.task_type)
        _string_tuple("depends_on_step_ids", self.depends_on_step_ids)
        if not isinstance(self.required_capabilities, CapabilityRequirement):
            raise TypeError("required_capabilities必须是CapabilityRequirement")
        _text("input_schema_version", self.input_schema_version)
        _text("output_schema_version", self.output_schema_version)
        _string_tuple("input_reference_ids", self.input_reference_ids)
        _string_set("allowed_tools", self.allowed_tools)
        _string_set("required_permissions", self.required_permissions)
        if not isinstance(self.budget, ExecutionBudget):
            raise TypeError("budget必须是ExecutionBudget")
        _string_tuple("expected_deliverable_ids", self.expected_deliverable_ids)
        _quality_check_set(self.quality_check_ids)
        if not isinstance(self.required, bool):
            raise TypeError("required必须是布尔值")
        if not isinstance(self.failure_behavior, FailureBehavior):
            raise TypeError("failure_behavior必须是FailureBehavior")
        if self.required and self.failure_behavior is FailureBehavior.SKIP_WITH_WARNING:
            raise ValueError("必需步骤不得带告警跳过")
        if (
            not self.required
            and self.failure_behavior is not FailureBehavior.SKIP_WITH_WARNING
        ):
            raise ValueError("可选步骤必须带告警跳过")


@dataclass(frozen=True, slots=True)
class PlanTemplateDefinition:
    """可复用的版本化多步骤计划模板，不拥有执行逻辑。"""

    contract_version: str
    template_id: str
    semantic_version: str
    success_conditions: tuple[str, ...]
    steps: tuple[ScenarioStepDefinition, ...]
    termination_conditions: frozenset[str]

    def __post_init__(self) -> None:
        if self.contract_version != "plan-template/1":
            raise ValueError("contract_version必须为plan-template/1")
        _stable_id("template_id", self.template_id)
        _semantic_version("semantic_version", self.semantic_version)
        _string_tuple("success_conditions", self.success_conditions)
        if not isinstance(self.steps, tuple):
            raise TypeError("steps必须是不可变元组")
        if any(not isinstance(step, ScenarioStepDefinition) for step in self.steps):
            raise TypeError("steps只能包含ScenarioStepDefinition")
        _string_set("termination_conditions", self.termination_conditions)


@dataclass(frozen=True, slots=True)
class ScenarioPackManifest:
    """运营场景包的版本化声明；不包含 Agent、Tool 或 Provider 实现。"""

    contract_version: str
    scenario_id: str
    semantic_version: str
    applicable_intents: frozenset[OperationIntent]
    trigger_conditions: tuple[KeyCondition, ...]
    required_condition_ids: frozenset[str]
    default_conditions: tuple[OperationAssumption, ...]
    clarification_policy: ClarificationPolicy
    recommended_strategy: StrategyMode
    plan_template: PlanTemplateDefinition
    profile_requirements: frozenset[ProfileKind]
    output_requirements: tuple[DeliverableRequirement, ...]
    quality_check_ids: frozenset[str]
    budget: ExecutionBudget
    termination_conditions: frozenset[str]
    failure_behavior: FailureBehavior

    def __post_init__(self) -> None:
        if self.contract_version != "scenario-pack/1":
            raise ValueError("contract_version必须为scenario-pack/1")
        _stable_id("scenario_id", self.scenario_id)
        _semantic_version("semantic_version", self.semantic_version)
        if (
            not isinstance(self.applicable_intents, frozenset)
            or not self.applicable_intents
        ):
            raise ValueError("applicable_intents必须是非空不可变集合")
        if any(
            not isinstance(item, OperationIntent) for item in self.applicable_intents
        ):
            raise TypeError("applicable_intents只能包含OperationIntent")
        if not isinstance(self.trigger_conditions, tuple):
            raise TypeError("trigger_conditions必须是不可变元组")
        if any(not isinstance(item, KeyCondition) for item in self.trigger_conditions):
            raise TypeError("trigger_conditions只能包含KeyCondition")
        _string_set("required_condition_ids", self.required_condition_ids)
        if not isinstance(self.default_conditions, tuple):
            raise TypeError("default_conditions必须是不可变元组")
        if any(
            not isinstance(item, OperationAssumption)
            for item in self.default_conditions
        ):
            raise TypeError("default_conditions只能包含OperationAssumption")
        if not isinstance(self.clarification_policy, ClarificationPolicy):
            raise TypeError("clarification_policy必须是ClarificationPolicy")
        if not isinstance(self.recommended_strategy, StrategyMode):
            raise TypeError("recommended_strategy必须是StrategyMode")
        if not isinstance(self.plan_template, PlanTemplateDefinition):
            raise TypeError("plan_template必须是PlanTemplateDefinition")
        if not isinstance(self.profile_requirements, frozenset):
            raise TypeError("profile_requirements必须是不可变集合")
        if any(not isinstance(item, ProfileKind) for item in self.profile_requirements):
            raise TypeError("profile_requirements只能包含ProfileKind")
        if not isinstance(self.output_requirements, tuple):
            raise TypeError("output_requirements必须是不可变元组")
        if any(
            not isinstance(item, DeliverableRequirement)
            for item in self.output_requirements
        ):
            raise TypeError("output_requirements只能包含DeliverableRequirement")
        _quality_check_set(self.quality_check_ids)
        if not isinstance(self.budget, ExecutionBudget):
            raise TypeError("budget必须是ExecutionBudget")
        _string_set("termination_conditions", self.termination_conditions)
        if not isinstance(self.failure_behavior, FailureBehavior):
            raise TypeError("failure_behavior必须是FailureBehavior")


def _budget_leq(child: ExecutionBudget, parent: ExecutionBudget) -> bool:
    return all(
        getattr(child, name) <= getattr(parent, name)
        for name in (
            "max_iterations",
            "max_tool_calls",
            "max_input_tokens",
            "max_output_tokens",
            "timeout_ms",
            "max_cost_microunits",
        )
    )


def _validate_template(
    template: PlanTemplateDefinition, manifest: ScenarioPackManifest
) -> None:
    if template.contract_version != "plan-template/1":
        raise ValueError("场景模板版本无效")
    if not template.steps:
        raise ValueError("场景模板必须至少包含一个步骤")
    if template.termination_conditions != manifest.termination_conditions:
        raise ValueError("场景终止条件与模板不一致")
    ids = [step.step_id for step in template.steps]
    if len(set(ids)) != len(ids):
        raise ValueError("场景步骤标识不得重复")
    known = set(ids)
    deps = {step.step_id: set(step.depends_on_step_ids) for step in template.steps}
    if any(dep not in known for values in deps.values() for dep in values):
        raise ValueError("场景步骤依赖不存在")
    while deps:
        ready = {step_id for step_id, values in deps.items() if not values}
        if not ready:
            raise ValueError("场景步骤存在循环依赖")
        for step_id in ready:
            deps.pop(step_id)
        for values in deps.values():
            values.difference_update(ready)
    declared_outputs = {item.requirement_id for item in manifest.output_requirements}
    if len(declared_outputs) != len(manifest.output_requirements):
        raise ValueError("场景输出要求标识不得重复")
    for step in template.steps:
        if not _budget_leq(step.budget, manifest.budget):
            raise ValueError("场景步骤预算不得超过清单预算")
        if not set(step.expected_deliverable_ids).issubset(declared_outputs):
            raise ValueError("场景步骤输出未声明")
        if not step.quality_check_ids.issubset(manifest.quality_check_ids):
            raise ValueError("场景步骤质量检查未声明")
    names = (
        "max_iterations",
        "max_tool_calls",
        "max_input_tokens",
        "max_output_tokens",
        "timeout_ms",
        "max_cost_microunits",
    )
    if any(
        max((getattr(step.budget, name) for step in template.steps), default=0)
        > getattr(manifest.budget, name)
        for name in names
    ):
        raise ValueError("场景步骤预算总和不得超过清单预算")


def validate_scenario_pack(manifest: ScenarioPackManifest) -> None:
    """校验场景清单、模板依赖、能力选择字段和预算，不执行场景。"""

    if not isinstance(manifest, ScenarioPackManifest):
        raise TypeError("manifest必须是ScenarioPackManifest")
    condition_ids = [item.condition_id for item in manifest.trigger_conditions]
    if len(condition_ids) != len(set(condition_ids)):
        raise ValueError("场景触发条件标识不得重复")
    declared = set(condition_ids)
    if not manifest.required_condition_ids.issubset(declared):
        raise ValueError("场景必需条件未声明")
    if any(item.condition_id not in declared for item in manifest.default_conditions):
        raise ValueError("场景默认条件未声明")
    _validate_template(manifest.plan_template, manifest)


def _steps_for_task(
    manifest: ScenarioPackManifest, task: OperationTaskSpec
) -> tuple[ScenarioStepDefinition, ...]:
    """多平台场景只编译用户明确请求的平台步骤。"""

    steps = manifest.plan_template.steps
    if manifest.scenario_id != "multi_platform_content":
        return steps
    platforms: tuple[str, ...] = ()
    for condition in task.key_conditions:
        if condition.condition_id != "platforms" or condition.value is None:
            continue
        raw = dict(condition.value.items).get("platforms")
        if isinstance(raw, tuple) and all(isinstance(item, str) for item in raw):
            platforms = tuple(item for item in raw if isinstance(item, str))
        break
    if not platforms:
        return steps
    requested: set[str] = set()
    for item in platforms:
        key = item.strip().lower()
        canonical = _PLATFORM_ALIASES.get(key)
        if canonical is None:
            raise ValueError("SCENARIO_PLATFORM_UNSUPPORTED")
        requested.add(canonical)
    deliverable_ids = {
        requirement.requirement_id
        for requirement in manifest.output_requirements
        if any(
            channel.strip().lower().replace("-", "_") in requested
            for channel in requirement.channel_ids
        )
    }
    selected = tuple(
        step
        for step in steps
        if step.expected_deliverable_ids
        and set(step.expected_deliverable_ids).issubset(deliverable_ids)
    )
    if not selected:
        raise ValueError("SCENARIO_PLATFORM_UNSUPPORTED")
    return selected


def compile_scenario_plan(
    manifest: ScenarioPackManifest,
    task: OperationTaskSpec,
    context: OperationContext,
    plan_id: str,
) -> OperationPlan:
    """把已经校验的模板逐字段映射为不可执行运营计划。"""

    validate_scenario_pack(manifest)
    if not isinstance(task, OperationTaskSpec):
        raise TypeError("task必须是OperationTaskSpec")
    if not isinstance(context, OperationContext):
        raise TypeError("context必须是OperationContext")
    if context.task_id != task.task_id:
        raise ValueError("context与task的任务标识不一致")
    _stable_id("plan_id", plan_id)
    selected_steps = _steps_for_task(manifest, task)
    plan = OperationPlan(
        "operation-plan/1",
        plan_id,
        task.task_id,
        manifest.recommended_strategy,
        manifest.plan_template.template_id,
        manifest.plan_template.semantic_version,
        manifest.plan_template.success_conditions,
        tuple(
            OperationPlanStep(
                step.step_id,
                step.task_type,
                step.depends_on_step_ids,
                step.required_capabilities,
                step.input_schema_version,
                step.output_schema_version,
                step.input_reference_ids,
                context,
                step.allowed_tools,
                step.required_permissions,
                step.budget,
                step.expected_deliverable_ids,
                step.quality_check_ids,
                step.required,
                step.failure_behavior,
            )
            for step in selected_steps
        ),
        manifest.budget,
        manifest.plan_template.termination_conditions,
    )
    validate_operation_plan(plan)
    return plan


__all__ = [
    "ClarificationPolicy",
    "PlanTemplateDefinition",
    "ScenarioPackManifest",
    "ScenarioStepDefinition",
    "compile_scenario_plan",
    "validate_scenario_pack",
]
