"""运营计划依赖、预算与失败策略校验。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.contracts.planning import (
    FailureBehavior,
    OperationPlan,
    OperationPlanStep,
    topological_step_ids,
    validate_operation_plan,
)
from efficiency_platform_agent.agents.operation.contracts.profiles import (
    OperationContext,
)
from efficiency_platform_agent.core.agent import CapabilityRequirement
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.run import ExecutionBudget


def _budget(output: int = 100) -> ExecutionBudget:
    return ExecutionBudget(4, 4, 400, output, 5000, 100)


def _context() -> OperationContext:
    return OperationContext(
        "operation-context/1", "context-a", "tenant-a", "task-a", (), frozenset()
    )


def _step(
    step_id: str,
    deps: tuple[str, ...] = (),
    *,
    budget: ExecutionBudget | None = None,
    required: bool = True,
    failure: FailureBehavior = FailureBehavior.FAIL,
) -> OperationPlanStep:
    return OperationPlanStep(
        step_id,
        "operation.research",
        deps,
        CapabilityRequirement(any_of=frozenset({"research"})),
        "input/1",
        "output/1",
        (),
        _context(),
        frozenset(),
        frozenset(),
        budget or _budget(),
        (),
        frozenset({"quality"}),
        required,
        failure,
    )


def _plan(steps: tuple[OperationPlanStep, ...]) -> OperationPlan:
    return OperationPlan(
        "operation-plan/1",
        "plan-a",
        "task-a",
        StrategyMode.DIRECT,
        None,
        None,
        ("done",),
        steps,
        _budget(400),
        frozenset({"done"}),
    )


class PlanningContractTest(unittest.TestCase):
    """验证计划只声明且严格校验依赖与预算。"""

    def test_rejects_cycle_and_unknown_dependency(self) -> None:
        with self.assertRaises(ValueError):
            validate_operation_plan(_plan((_step("a", ("b",)), _step("b", ("a",)))))
        with self.assertRaises(ValueError):
            validate_operation_plan(_plan((_step("a", ("missing",)),)))

    def test_rejects_budget_oversubscription(self) -> None:
        with self.assertRaises(ValueError):
            plan = _plan((_step("a", budget=_budget(101)),))
            validate_operation_plan(
                OperationPlan(
                    plan.contract_version,
                    plan.plan_id,
                    plan.task_id,
                    plan.strategy,
                    plan.source_template_id,
                    plan.source_template_version,
                    plan.success_conditions,
                    plan.steps,
                    _budget(100),
                    plan.termination_conditions,
                )
            )

    def test_topological_order_is_stable(self) -> None:
        plan = _plan(
            (_step("content", ("research",)), _step("brand"), _step("research"))
        )
        self.assertEqual(topological_step_ids(plan), ("brand", "research", "content"))

    def test_failure_behavior_matches_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "可选步骤必须带告警跳过"):
            _step("optional", required=False)
        with self.assertRaisesRegex(ValueError, "必需步骤不得带告警跳过"):
            _step("required", failure=FailureBehavior.SKIP_WITH_WARNING)

    def test_rejects_partial_template_reference(self) -> None:
        with self.assertRaisesRegex(ValueError, "模板 ID 与版本必须同时提供"):
            OperationPlan(
                "operation-plan/1",
                "p",
                "t",
                StrategyMode.DIRECT,
                "template",
                None,
                (),
                (),
                _budget(400),
                frozenset({"done"}),
            )


if __name__ == "__main__":
    unittest.main()
