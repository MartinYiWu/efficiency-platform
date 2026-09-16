"""Scenario Pack 清单、计划模板和 S2 窄端口的离线契约测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.contracts import (
    ClarificationPolicy,
    DeliverableKind,
    DeliverableRequirement,
    FailureBehavior,
    KeyCondition,
    OperationIntent,
    OperationPlan,
    PlanTemplateDefinition,
    ScenarioPackManifest,
    ScenarioStepDefinition,
    compile_scenario_plan,
    validate_scenario_pack,
)
from efficiency_platform_agent.core.agent import CapabilityRequirement
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.run import ExecutionBudget
from tests.support.s2_operation_fakes import (
    FakeS2OperationAssemblyPort,
    FakeS2OperationIntentPort,
    FakeS2OperationPlanningPort,
    build_context,
    build_empty_evidence_pack,
    build_operation_request,
)


def _budget() -> ExecutionBudget:
    return ExecutionBudget(4, 4, 400, 400, 2_000, 100)


def _requirement(name: str) -> CapabilityRequirement:
    return CapabilityRequirement(all_of=frozenset({name}))


def _deliverable_requirement(requirement_id: str = "report") -> DeliverableRequirement:
    return DeliverableRequirement(
        requirement_id,
        DeliverableKind.REPORT,
        1,
        ("web",),
        "markdown",
        "article",
        frozenset({"quality.source"}),
    )


def _step(
    step_id: str,
    task_type: str,
    capability: str,
    *,
    depends_on: tuple[str, ...] = (),
    output_ids: tuple[str, ...] = ("report",),
    required: bool = True,
) -> ScenarioStepDefinition:
    return ScenarioStepDefinition(
        "scenario-step/1",
        "1.0.0",
        step_id,
        task_type,
        depends_on,
        _requirement(capability),
        f"{task_type}-input/1",
        f"{task_type}-output/1",
        (),
        frozenset({"public.search"}),
        frozenset({"public.read"}),
        _budget(),
        output_ids,
        frozenset({"quality.source"}),
        required,
        FailureBehavior.FAIL if required else FailureBehavior.SKIP_WITH_WARNING,
    )


def _template(
    steps: tuple[ScenarioStepDefinition, ...] | None = None,
) -> PlanTemplateDefinition:
    return PlanTemplateDefinition(
        "plan-template/1",
        "operation-report",
        "1.0.0",
        ("all_required_steps_succeeded",),
        steps or (_step("research", "operation.research", "operation.research"),),
        frozenset({"stop_on_failure"}),
    )


def _manifest(
    *,
    trigger_conditions: tuple[KeyCondition, ...] = (),
    required_condition_ids: frozenset[str] = frozenset(),
    output_requirements: tuple[DeliverableRequirement, ...] = (
        _deliverable_requirement(),
    ),
    plan_template: PlanTemplateDefinition | None = None,
) -> ScenarioPackManifest:
    return ScenarioPackManifest(
        "scenario-pack/1",
        "operation-report",
        "1.0.0",
        frozenset({OperationIntent.RESEARCH}),
        trigger_conditions,
        required_condition_ids,
        (),
        ClarificationPolicy.ASK_USER,
        StrategyMode.WORKFLOW,
        plan_template or _template(),
        frozenset(),
        output_requirements,
        frozenset({"quality.source"}),
        _budget(),
        frozenset({"stop_on_failure"}),
        FailureBehavior.FAIL,
    )


class ScenarioPackTests(unittest.TestCase):
    def test_scenario_step_constructor_rejects_unstable_identity_and_mutable_sets(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "step_id"):
            _step("Bad-ID", "operation.research", "operation.research")

        with self.assertRaisesRegex(TypeError, "allowed_tools"):
            ScenarioStepDefinition(
                "scenario-step/1",
                "1.0.0",
                "research",
                "operation.research",
                (),
                _requirement("operation.research"),
                "operation-research-input/1",
                "operation-research-output/1",
                (),
                {"public.search"},  # type: ignore[arg-type]
                frozenset({"public.read"}),
                _budget(),
                ("report",),
                frozenset({"quality.source"}),
                True,
                FailureBehavior.FAIL,
            )

    def test_manifest_constructor_rejects_wrong_version_and_strategy_type(self) -> None:
        with self.assertRaisesRegex(ValueError, "contract_version"):
            ScenarioPackManifest(
                "scenario-pack/2",
                "operation-report",
                "1.0.0",
                frozenset({OperationIntent.RESEARCH}),
                (),
                frozenset(),
                (),
                ClarificationPolicy.ASK_USER,
                StrategyMode.WORKFLOW,
                _template(),
                frozenset(),
                (_deliverable_requirement(),),
                frozenset({"quality.source"}),
                _budget(),
                frozenset({"stop_on_failure"}),
                FailureBehavior.FAIL,
            )

        with self.assertRaisesRegex(TypeError, "recommended_strategy"):
            ScenarioPackManifest(
                "scenario-pack/1",
                "operation-report",
                "1.0.0",
                frozenset({OperationIntent.RESEARCH}),
                (),
                frozenset(),
                (),
                ClarificationPolicy.ASK_USER,
                "workflow",  # type: ignore[arg-type]
                _template(),
                frozenset(),
                (_deliverable_requirement(),),
                frozenset({"quality.source"}),
                _budget(),
                frozenset({"stop_on_failure"}),
                FailureBehavior.FAIL,
            )

    def test_manifest_validator_rejects_missing_required_trigger_with_own_error(
        self,
    ) -> None:
        candidate = _manifest(
            required_condition_ids=frozenset({"brand"}),
            trigger_conditions=(),
        )
        with self.assertRaisesRegex(ValueError, "场景必需条件未声明"):
            validate_scenario_pack(candidate)

    def test_manifest_validator_rejects_undeclared_step_output_without_constructor_false_positive(
        self,
    ) -> None:
        candidate = _manifest(
            output_requirements=(_deliverable_requirement("report"),),
            plan_template=_template(
                (
                    _step(
                        "research",
                        "operation.research",
                        "operation.research",
                        output_ids=("undeclared",),
                    ),
                )
            ),
        )
        with self.assertRaisesRegex(ValueError, "场景步骤输出未声明"):
            validate_scenario_pack(candidate)

    def test_multi_expert_template_compiles_one_to_one_to_operation_plan(self) -> None:
        candidate = _manifest(
            plan_template=_template(
                (
                    _step("research", "operation.research", "operation.research"),
                    _step(
                        "compose",
                        "operation.compose",
                        "operation.compose",
                        depends_on=("research",),
                    ),
                )
            )
        )
        validate_scenario_pack(candidate)
        task = FakeS2OperationIntentPort().normalize(build_operation_request())
        plan = compile_scenario_plan(candidate, task, build_context(task), "plan-a")
        self.assertIsInstance(plan, OperationPlan)
        self.assertEqual(
            tuple(step.step_id for step in plan.steps), ("research", "compose")
        )
        self.assertEqual(
            (plan.source_template_id, plan.source_template_version),
            (
                candidate.plan_template.template_id,
                candidate.plan_template.semantic_version,
            ),
        )
        self.assertEqual(plan.steps[1].depends_on_step_ids, ("research",))
        self.assertEqual(
            tuple(step.required_capabilities.all_of for step in plan.steps),
            (frozenset({"operation.research"}), frozenset({"operation.compose"})),
        )
        self.assertTrue(plan.steps[0].required)

    def test_fake_s2_ports_produce_only_declared_contracts(self) -> None:
        task = FakeS2OperationIntentPort().normalize(build_operation_request())
        plan = FakeS2OperationPlanningPort().build_plan(task, build_context(task))
        bundle = FakeS2OperationAssemblyPort().assemble(
            task,
            plan,
            build_empty_evidence_pack(task.task_id),
        )
        self.assertEqual(bundle.task_id, task.task_id)
        self.assertEqual(bundle.plan_id, plan.plan_id)


if __name__ == "__main__":
    unittest.main()
