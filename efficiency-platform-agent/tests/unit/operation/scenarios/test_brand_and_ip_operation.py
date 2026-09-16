"""品牌与 IP 运营场景包的离线回归测试。"""

from __future__ import annotations

from dataclasses import replace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from efficiency_platform_agent.agents.operation.scenarios.contracts import (
    ScenarioExecutionResult,
)
from efficiency_platform_agent.agents.operation.scenarios.manifests import (
    build_s6_manifests,
)
from efficiency_platform_agent.agents.operation.scenarios.service import (
    ScenarioPackService,
)
from efficiency_platform_agent.core.multi_agent import CompletionStatus
from tests.support.s2_operation_fakes import (
    FakeS2OperationAssemblyPort,
    FakeS2OperationPlanningPort,
    build_context,
    build_empty_evidence_pack,
)
from tests.support.s6_scenario_samples import sample_by_id, submission_from_sample


class _Registry:
    def __init__(self) -> None:
        self._items = {
            (item.scenario_id, item.semantic_version): item
            for item in build_s6_manifests()
        }

    def get(self, scenario_id: str, semantic_version: str):
        return self._items[(scenario_id, semantic_version)]


class _Supervisor:
    def __init__(
        self,
        scenario_id: str,
        status: CompletionStatus,
        completed: tuple[str, ...],
        missing: tuple[str, ...],
        warnings=frozenset(),
    ):
        self.scenario_id, self.status, self.completed, self.missing, self.warnings = (
            scenario_id,
            status,
            completed,
            missing,
            warnings,
        )
        self.requests = []

    async def execute_scenario(self, request):
        self.requests.append(request)
        evidence = request.evidence_pack or build_empty_evidence_pack(
            request.task_spec.task_id
        )
        bundle = (
            FakeS2OperationAssemblyPort().assemble(
                request.task_spec, request.operation_plan, evidence
            )
            if self.completed
            else None
        )
        return ScenarioExecutionResult(
            self.scenario_id,
            "1.0.0",
            self.status,
            bundle,
            None,
            (),
            self.completed,
            self.missing,
            self.warnings,
            None,
        )


def _submission(sample_id: str, *, waiting: bool = False):
    submission = submission_from_sample(sample_by_id(sample_id))
    if waiting:
        condition = (
            "brand-goal"
            if submission.scenario_id == "brand_operation_plan"
            else "ip-audience"
        )
        submission = replace(
            submission,
            task_spec=replace(
                submission.task_spec,
                missing_critical_condition_ids=(condition,),
                requires_user_input=True,
            ),
        )
    return submission


class BrandAndIPOperationScenarioTests(IsolatedAsyncioTestCase):
    async def _run(self, sample_id: str, supervisor: _Supervisor, *, waiting=False):
        submission = _submission(sample_id, waiting=waiting)
        context = build_context(submission.task_spec)
        plan = FakeS2OperationPlanningPort().build_plan(submission.task_spec, context)
        with (
            patch(
                "efficiency_platform_agent.agents.operation.scenarios.service.select_profiles_for_task",
                return_value=context,
            ),
            patch(
                "efficiency_platform_agent.agents.operation.scenarios.service.compile_scenario_plan",
                return_value=plan,
            ),
        ):
            return await ScenarioPackService(_Registry(), supervisor).run(submission)

    async def test_brand_complete_returns_strategy(self) -> None:
        result = await self._run(
            "brand_operation_plan.complete/1",
            _Supervisor(
                "brand_operation_plan",
                CompletionStatus.COMPLETE,
                ("brand-strategy",),
                (),
            ),
        )
        self.assertEqual(result.completion_status, CompletionStatus.COMPLETE)
        self.assertEqual(result.completed_scope, ("brand-strategy",))

    async def test_brand_research_unavailable_is_not_success(self) -> None:
        result = await self._run(
            "brand_operation_plan.research-unavailable/1",
            _Supervisor(
                "brand_operation_plan",
                CompletionStatus.PARTIAL,
                ("brand-strategy",),
                (),
                frozenset({"RESEARCH_UNAVAILABLE"}),
            ),
        )
        self.assertNotEqual(result.completion_status, CompletionStatus.COMPLETE)
        self.assertIn("RESEARCH_UNAVAILABLE", result.warning_codes)

    async def test_brand_goal_waits_without_supervisor(self) -> None:
        supervisor = _Supervisor(
            "brand_operation_plan",
            CompletionStatus.WAITING_INPUT,
            (),
            ("brand-strategy",),
        )
        result = await self._run(
            "brand_operation_plan.waiting-brand-goal/1", supervisor, waiting=True
        )
        self.assertEqual(result.completion_status, CompletionStatus.WAITING_INPUT)
        self.assertEqual(supervisor.requests, [])

    async def test_ip_complete_returns_positioning(self) -> None:
        result = await self._run(
            "ip_operation_plan.complete/1",
            _Supervisor(
                "ip_operation_plan", CompletionStatus.COMPLETE, ("ip-positioning",), ()
            ),
        )
        self.assertEqual(result.completion_status, CompletionStatus.COMPLETE)

    async def test_ip_channel_unavailable_preserves_strategy_scope(self) -> None:
        result = await self._run(
            "ip_operation_plan.channel-unavailable/1",
            _Supervisor(
                "ip_operation_plan",
                CompletionStatus.PARTIAL,
                ("ip-positioning", "incubation-path"),
                ("platform-content",),
                frozenset({"CHANNEL_UNAVAILABLE"}),
            ),
        )
        self.assertEqual(result.completion_status, CompletionStatus.PARTIAL)
        self.assertIn("ip-positioning", result.completed_scope)
        self.assertIn("incubation-path", result.completed_scope)
        self.assertIn("CHANNEL_UNAVAILABLE", result.warning_codes)

    async def test_ip_audience_waits_without_supervisor(self) -> None:
        supervisor = _Supervisor(
            "ip_operation_plan", CompletionStatus.WAITING_INPUT, (), ("ip-positioning",)
        )
        result = await self._run(
            "ip_operation_plan.waiting-ip-audience/1", supervisor, waiting=True
        )
        self.assertEqual(result.completion_status, CompletionStatus.WAITING_INPUT)
        self.assertEqual(supervisor.requests, [])


__all__ = ["BrandAndIPOperationScenarioTests"]
