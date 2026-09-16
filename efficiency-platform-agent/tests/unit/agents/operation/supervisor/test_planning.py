"""受限运营任务 DAG 编译测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.contracts.planning import (
    FailureBehavior,
    OperationPlan,
    OperationPlanStep,
)
from efficiency_platform_agent.agents.operation.contracts.profiles import (
    OperationContext,
)
from efficiency_platform_agent.agents.operation.supervisor.errors import (
    SupervisorPlanError,
    SupervisorPlanErrorCode,
)
from efficiency_platform_agent.agents.operation.supervisor.planning import (
    OperationPlanCompiler,
)
from efficiency_platform_agent.core.agent import CapabilityRequirement
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.multi_agent import (
    SupervisorLimits,
    TaskFailureMode,
)
from efficiency_platform_agent.core.run import ExecutionBudget

_BUDGET = ExecutionBudget(4, 4, 100, 100, 1_000, 100)
_CONTEXT = OperationContext(
    contract_version="operation-context/1",
    context_id="context-a",
    tenant_id="tenant-a",
    task_id="task-a",
    profile_references=(),
    source_scope_ids=frozenset(),
)


def _step(
    step_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    required: bool = True,
    failure_behavior: FailureBehavior = FailureBehavior.FAIL,
    budget: ExecutionBudget = _BUDGET,
) -> OperationPlanStep:
    return OperationPlanStep(
        step_id=step_id,
        task_type=f"operation.{step_id}",
        depends_on_step_ids=depends_on,
        required_capabilities=CapabilityRequirement(
            all_of=frozenset({f"operation.{step_id}"})
        ),
        input_schema_version=f"operation-{step_id}-input/1",
        output_schema_version=f"operation-{step_id}-output/1",
        input_reference_ids=(),
        context=_CONTEXT,
        allowed_tools=frozenset({f"operation.{step_id}.tool"}),
        required_permissions=frozenset({"public.read"}),
        budget=budget,
        expected_deliverable_ids=(f"deliverable-{step_id}",),
        quality_check_ids=frozenset(),
        required=required,
        failure_behavior=failure_behavior,
    )


def _plan(
    steps: tuple[OperationPlanStep, ...],
    *,
    total_budget: ExecutionBudget = _BUDGET,
) -> OperationPlan:
    return OperationPlan(
        contract_version="operation-plan/1",
        plan_id="plan-a",
        task_id="task-a",
        strategy=StrategyMode.MULTI_AGENT,
        source_template_id="operation-template",
        source_template_version="1.0.0",
        success_conditions=("全部必需步骤完成",),
        steps=steps,
        total_budget=total_budget,
        termination_conditions=frozenset({"完成", "失败"}),
    )


class OperationPlanCompilerTest(unittest.TestCase):
    """验证 DAG 编译的字段保真与失败关闭。"""

    def test_compile_preserves_stable_topology_and_selection_fields(self) -> None:
        steps = (
            _step("assemble", depends_on=("draft_a", "draft_b")),
            _step("draft_b", depends_on=("prepare",)),
            _step("prepare"),
            _step("draft_a", depends_on=("prepare",)),
        )
        graph = OperationPlanCompiler(SupervisorLimits()).compile(_plan(steps))
        self.assertEqual(
            graph.topological_order,
            ("prepare", "draft_a", "draft_b", "assemble"),
        )
        by_id = {item.task_id: item for item in graph.tasks}
        source = next(item for item in steps if item.step_id == "draft_a")
        target = by_id["draft_a"]
        self.assertEqual(
            (
                target.task_type,
                target.input_schema_version,
                target.output_schema_version,
                target.required_permissions,
                target.allowed_tools,
                target.required,
                target.failure_mode,
                target.capability_requirement,
            ),
            (
                source.task_type,
                source.input_schema_version,
                source.output_schema_version,
                source.required_permissions,
                source.allowed_tools,
                source.required,
                TaskFailureMode.FAIL_PLAN,
                source.required_capabilities,
            ),
        )
        self.assertEqual(graph.plan_contract_version, "operation-plan/1")

    def test_compile_maps_all_failure_behaviors(self) -> None:
        steps = (
            _step("fail"),
            _step("input", failure_behavior=FailureBehavior.REQUEST_INPUT),
            _step("retry", failure_behavior=FailureBehavior.RETRY_ONCE),
            _step(
                "skip",
                required=False,
                failure_behavior=FailureBehavior.SKIP_WITH_WARNING,
            ),
        )
        graph = OperationPlanCompiler(SupervisorLimits()).compile(_plan(steps))
        self.assertEqual(
            {item.task_id: item.failure_mode for item in graph.tasks},
            {
                "fail": TaskFailureMode.FAIL_PLAN,
                "input": TaskFailureMode.WAIT_INPUT,
                "retry": TaskFailureMode.RETRY_ONCE,
                "skip": TaskFailureMode.SKIP_WITH_WARNING,
            },
        )

    def test_compile_rejects_empty_plan(self) -> None:
        with self.assertRaisesRegex(SupervisorPlanError, "PLAN_EMPTY"):
            OperationPlanCompiler(SupervisorLimits()).compile(_plan(()))

    def test_compile_rejects_cycle_before_dispatch(self) -> None:
        plan = _plan((_step("a", depends_on=("b",)), _step("b", depends_on=("a",))))
        with self.assertRaisesRegex(SupervisorPlanError, "DAG_CYCLE"):
            OperationPlanCompiler(SupervisorLimits()).compile(plan)

    def test_compile_rejects_missing_dependency(self) -> None:
        with self.assertRaisesRegex(SupervisorPlanError, "DEPENDENCY_NOT_FOUND"):
            OperationPlanCompiler(SupervisorLimits()).compile(
                _plan((_step("a", depends_on=("missing",)),))
            )

    def test_compile_rejects_task_limit(self) -> None:
        steps = tuple(_step(f"task-{index:02d}") for index in range(17))
        with self.assertRaisesRegex(SupervisorPlanError, "TASK_LIMIT_EXCEEDED"):
            OperationPlanCompiler(SupervisorLimits()).compile(_plan(steps))

    def test_compile_rejects_depth_limit(self) -> None:
        steps = tuple(
            _step(f"step-{index:02d}", depends_on=(f"step-{index - 1:02d}",))
            if index
            else _step("step-00")
            for index in range(9)
        )
        with self.assertRaisesRegex(SupervisorPlanError, "DAG_DEPTH_EXCEEDED"):
            OperationPlanCompiler(SupervisorLimits()).compile(_plan(steps))

    def test_compile_rejects_step_budget_exceeding_plan(self) -> None:
        excessive = ExecutionBudget(5, 4, 100, 100, 1_000, 100)
        with self.assertRaisesRegex(SupervisorPlanError, "STEP_BUDGET_EXCEEDS_PLAN"):
            OperationPlanCompiler(SupervisorLimits()).compile(
                _plan((_step("a", budget=excessive),))
            )

    def test_error_code_is_structured_and_stable(self) -> None:
        self.assertEqual(SupervisorPlanErrorCode.PLAN_EMPTY.value, "PLAN_EMPTY")


if __name__ == "__main__":
    unittest.main()
