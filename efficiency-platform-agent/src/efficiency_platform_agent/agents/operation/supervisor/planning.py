"""把 S3 运营计划编译为受限的 S4 任务图。"""

from __future__ import annotations

from efficiency_platform_agent.core.multi_agent import (
    SupervisorLimits,
    TaskFailureMode,
    TaskGraph,
    TaskNode,
)
from efficiency_platform_agent.core.run import JsonObject

from ..contracts.planning import FailureBehavior, OperationPlan, OperationPlanStep
from .errors import SupervisorPlanError, SupervisorPlanErrorCode

_FAILURE_MODES = {
    FailureBehavior.FAIL: TaskFailureMode.FAIL_PLAN,
    FailureBehavior.REQUEST_INPUT: TaskFailureMode.WAIT_INPUT,
    FailureBehavior.RETRY_ONCE: TaskFailureMode.RETRY_ONCE,
    FailureBehavior.SKIP_WITH_WARNING: TaskFailureMode.SKIP_WITH_WARNING,
}


def _budget_within(child: object, parent: object) -> bool:
    """逐字段确认子步骤预算未超过计划预算。"""
    return all(
        getattr(child, field) <= getattr(parent, field)
        for field in (
            "max_iterations",
            "max_tool_calls",
            "max_input_tokens",
            "max_output_tokens",
            "timeout_ms",
            "max_cost_microunits",
        )
    )


def _stable_topological_order(steps: tuple[OperationPlanStep, ...]) -> tuple[str, ...]:
    """使用 Kahn 算法并按步骤标识排序，生成确定性拓扑序。"""
    known = {step.step_id for step in steps}
    dependencies = {step.step_id: set(step.depends_on_step_ids) for step in steps}
    for step in steps:
        missing = dependencies[step.step_id] - known
        if missing:
            raise SupervisorPlanError(
                SupervisorPlanErrorCode.DEPENDENCY_NOT_FOUND,
                "步骤依赖不存在",
                task_id=step.step_id,
            )
    result: list[str] = []
    while dependencies:
        ready = sorted(
            step_id for step_id, required in dependencies.items() if not required
        )
        if not ready:
            raise SupervisorPlanError(
                SupervisorPlanErrorCode.DAG_CYCLE,
                "计划步骤存在循环依赖",
            )
        result.extend(ready)
        for step_id in ready:
            dependencies.pop(step_id)
        for required in dependencies.values():
            required.difference_update(ready)
    return tuple(result)


def _depth(steps: tuple[OperationPlanStep, ...]) -> int:
    """计算计划依赖图的最长路径长度。"""
    by_id = {step.step_id: step for step in steps}
    memo: dict[str, int] = {}

    def visit(step_id: str, visiting: frozenset[str]) -> int:
        if step_id in memo:
            return memo[step_id]
        if step_id in visiting:
            raise SupervisorPlanError(
                SupervisorPlanErrorCode.DAG_CYCLE,
                "计划步骤存在循环依赖",
            )
        step = by_id[step_id]
        value = 1 + max(
            (visit(dep, visiting | {step_id}) for dep in step.depends_on_step_ids),
            default=0,
        )
        memo[step_id] = value
        return value

    return max((visit(step.step_id, frozenset()) for step in steps), default=0)


class OperationPlanCompiler:
    """在不创建 Agent 或调度器的前提下编译受限任务图。"""

    def __init__(self, limits: SupervisorLimits) -> None:
        if not isinstance(limits, SupervisorLimits):
            raise TypeError("limits 必须是 SupervisorLimits")
        self._limits = limits

    def compile(self, plan: OperationPlan) -> TaskGraph:
        """校验 S3 计划并逐字段复制为不可变 S4 TaskGraph。"""
        if not isinstance(plan, OperationPlan):
            raise TypeError("plan 必须是 OperationPlan")
        steps = plan.steps
        if not isinstance(steps, tuple) or not steps:
            raise SupervisorPlanError(
                SupervisorPlanErrorCode.PLAN_EMPTY,
                "计划步骤不能为空",
            )
        if len(steps) > self._limits.max_task_count:
            raise SupervisorPlanError(
                SupervisorPlanErrorCode.TASK_LIMIT_EXCEEDED,
                "计划任务数超过上限",
            )
        if any(not isinstance(step, OperationPlanStep) for step in steps):
            raise TypeError("计划只能包含 OperationPlanStep")
        ids = tuple(step.step_id for step in steps)
        if len(set(ids)) != len(ids):
            raise SupervisorPlanError(
                SupervisorPlanErrorCode.DUPLICATE_TASK_ID,
                "计划步骤标识不得重复",
            )
        for step in steps:
            if (
                step.required
                and step.failure_behavior is FailureBehavior.SKIP_WITH_WARNING
            ) or (
                not step.required
                and step.failure_behavior is not FailureBehavior.SKIP_WITH_WARNING
            ):
                raise SupervisorPlanError(
                    SupervisorPlanErrorCode.INVALID_FAILURE_BEHAVIOR,
                    "步骤 required 与失败行为不匹配",
                    task_id=step.step_id,
                )
            if not _budget_within(step.budget, plan.total_budget):
                raise SupervisorPlanError(
                    SupervisorPlanErrorCode.STEP_BUDGET_EXCEEDS_PLAN,
                    "步骤预算超过计划总预算",
                    task_id=step.step_id,
                )

        order = _stable_topological_order(steps)
        if _depth(steps) > self._limits.max_dag_depth:
            raise SupervisorPlanError(
                SupervisorPlanErrorCode.DAG_DEPTH_EXCEEDED,
                "计划 DAG 深度超过上限",
            )
        task_nodes = tuple(self._to_task_node(step) for step in steps)
        return TaskGraph(
            plan_id=plan.plan_id,
            plan_contract_version=plan.contract_version,
            plan_revision=0,
            tasks=task_nodes,
            topological_order=order,
        )

    @staticmethod
    def _to_task_node(step: OperationPlanStep) -> TaskNode:
        """把单个 S3 步骤映射为 S4 节点，不改变源对象。"""
        failure_mode = _FAILURE_MODES.get(step.failure_behavior)
        if failure_mode is None:
            raise SupervisorPlanError(
                SupervisorPlanErrorCode.INVALID_FAILURE_BEHAVIOR,
                "步骤失败行为未知",
                task_id=step.step_id,
            )
        context_view = JsonObject(
            (
                ("context_id", step.context.context_id),
                ("tenant_id", step.context.tenant_id),
                ("task_id", step.context.task_id),
            )
        )
        return TaskNode(
            task_id=step.step_id,
            task_type=step.task_type,
            capability_requirement=step.required_capabilities,
            input_schema_version=step.input_schema_version,
            output_schema_version=step.output_schema_version,
            depends_on=tuple(step.depends_on_step_ids),
            required=step.required,
            failure_mode=failure_mode,
            input_reference_ids=tuple(step.input_reference_ids),
            context_view=context_view,
            allowed_tools=frozenset(step.allowed_tools),
            required_permissions=frozenset(step.required_permissions),
            requested_budget=step.budget,
            expected_deliverable_ids=tuple(step.expected_deliverable_ids),
            quality_check_ids=frozenset(step.quality_check_ids),
        )


__all__ = ["OperationPlanCompiler"]
