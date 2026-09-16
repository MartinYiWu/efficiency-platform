"""运营计划的声明性步骤、预算和依赖图校验。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from efficiency_platform_agent.core.agent import CapabilityRequirement
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.run import ExecutionBudget

from .profiles import OperationContext


class FailureBehavior(StrEnum):
    """步骤失败后的声明性处理方式，不代表实际执行。"""

    FAIL = "fail"
    REQUEST_INPUT = "request_input"
    RETRY_ONCE = "retry_once"
    SKIP_WITH_WARNING = "skip_with_warning"


@dataclass(frozen=True, slots=True)
class OperationPlanStep:
    """供后续编排选择的单个计划步骤。"""

    step_id: str
    task_type: str
    depends_on_step_ids: tuple[str, ...]
    required_capabilities: CapabilityRequirement
    input_schema_version: str
    output_schema_version: str
    input_reference_ids: tuple[str, ...]
    context: OperationContext
    allowed_tools: frozenset[str]
    required_permissions: frozenset[str]
    budget: ExecutionBudget
    expected_deliverable_ids: tuple[str, ...]
    quality_check_ids: frozenset[str]
    required: bool
    failure_behavior: FailureBehavior

    def __post_init__(self) -> None:
        if not self.step_id or not self.task_type:
            raise ValueError("步骤标识和任务类型不能为空")
        if not self.input_schema_version or not self.output_schema_version:
            raise ValueError("输入输出 Schema 版本不能为空")
        if not isinstance(self.required_capabilities, CapabilityRequirement):
            raise TypeError("required_capabilities 类型无效")
        if self.required and self.failure_behavior is FailureBehavior.SKIP_WITH_WARNING:
            raise ValueError("必需步骤不得带告警跳过")
        if (
            not self.required
            and self.failure_behavior is not FailureBehavior.SKIP_WITH_WARNING
        ):
            raise ValueError("可选步骤必须带告警跳过")


@dataclass(frozen=True, slots=True)
class OperationPlan:
    """只描述运营步骤及其依赖的不可变计划。"""

    contract_version: str
    plan_id: str
    task_id: str
    strategy: StrategyMode
    source_template_id: str | None
    source_template_version: str | None
    success_conditions: tuple[str, ...]
    steps: tuple[OperationPlanStep, ...]
    total_budget: ExecutionBudget
    termination_conditions: frozenset[str]

    def __post_init__(self) -> None:
        if not self.contract_version or not self.plan_id or not self.task_id:
            raise ValueError("计划版本、计划标识和任务标识不能为空")
        if (self.source_template_id is None) != (self.source_template_version is None):
            raise ValueError("模板 ID 与版本必须同时提供")


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


def validate_operation_plan(plan: OperationPlan) -> None:
    """校验计划引用、无环依赖和预算，不执行任何步骤。"""
    if not isinstance(plan, OperationPlan):
        raise TypeError("plan 必须是 OperationPlan")
    ids = [step.step_id for step in plan.steps]
    if len(set(ids)) != len(ids):
        raise ValueError("步骤标识不得重复")
    known = set(ids)
    for step in plan.steps:
        if any(dep not in known for dep in step.depends_on_step_ids):
            raise ValueError("步骤依赖不存在")
        if not _budget_leq(step.budget, plan.total_budget):
            raise ValueError("子预算不得超过总预算")
    totals = {
        # 每一步预算是父预算内的执行上限；并行步骤不把同一父预算重复相加。
        name: max((getattr(step.budget, name) for step in plan.steps), default=0)
        for name in (
            "max_iterations",
            "max_tool_calls",
            "max_input_tokens",
            "max_output_tokens",
            "timeout_ms",
            "max_cost_microunits",
        )
    }
    if any(totals[name] > getattr(plan.total_budget, name) for name in totals):
        raise ValueError("步骤预算总和不得超过计划总预算")
    topological_step_ids(plan)


def topological_step_ids(plan: OperationPlan) -> tuple[str, ...]:
    """按依赖和步骤标识字典序生成稳定拓扑顺序。"""
    ids = {step.step_id for step in plan.steps}
    deps = {step.step_id: set(step.depends_on_step_ids) for step in plan.steps}
    if len(ids) != len(plan.steps) or any(
        dep not in ids for values in deps.values() for dep in values
    ):
        raise ValueError("步骤依赖不存在或步骤标识重复")
    result: list[str] = []
    while deps:
        ready = sorted(step_id for step_id, required in deps.items() if not required)
        if not ready:
            raise ValueError("计划步骤存在循环依赖")
        result.extend(ready)
        for step_id in ready:
            deps.pop(step_id)
        for required in deps.values():
            required.difference_update(ready)
    return tuple(result)


__all__ = [
    "FailureBehavior",
    "OperationPlan",
    "OperationPlanStep",
    "topological_step_ids",
    "validate_operation_plan",
]
