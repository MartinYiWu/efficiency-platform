"""行业动态场景包的离线回归测试。"""

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
        warning_codes: frozenset[str] = frozenset(),
    ) -> None:
        self.scenario_id = scenario_id
        self.status = status
        self.warning_codes = warning_codes
        self.requests = []

    async def execute_scenario(self, request):
        self.requests.append(request)
        complete = self.status is not CompletionStatus.WAITING_INPUT
        evidence = request.evidence_pack or build_empty_evidence_pack(
            request.task_spec.task_id
        )
        bundle = (
            FakeS2OperationAssemblyPort().assemble(
                request.task_spec, request.operation_plan, evidence
            )
            if complete
            else None
        )
        return ScenarioExecutionResult(
            self.scenario_id,
            "1.0.0",
            self.status,
            bundle,
            None,
            (),
            ("industry-report",) if complete else (),
            () if complete else ("industry-report",),
            self.warning_codes,
            None,
        )


def _submission(sample_id: str, *, waiting: bool = False):
    sample = sample_by_id(sample_id)
    submission = submission_from_sample(sample)
    if not waiting:
        return submission
    task = replace(
        submission.task_spec,
        missing_critical_condition_ids=("time-window",),
        requires_user_input=True,
    )
    return replace(submission, task_spec=task)


class IndustryDigestScenarioTests(IsolatedAsyncioTestCase):
    async def _run(
        self,
        sample_id: str,
        status: CompletionStatus,
        warnings=frozenset(),
        *,
        waiting=False,
    ):
        submission = _submission(sample_id, waiting=waiting)
        supervisor = _Supervisor(submission.scenario_id, status, warnings)
        service = ScenarioPackService(_Registry(), supervisor)
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
            return await service.run(submission), supervisor

    async def test_complete_digest_keeps_report_scope(self) -> None:
        result, supervisor = await self._run(
            "industry_digest.complete/1", CompletionStatus.COMPLETE
        )
        self.assertEqual(result.completion_status, CompletionStatus.COMPLETE)
        self.assertEqual(result.completed_scope, ("industry-report",))
        self.assertEqual(len(supervisor.requests), 1)

    async def test_digest_requires_topic_and_time_window(self) -> None:
        result, supervisor = await self._run(
            "industry_digest.waiting-time-window/1",
            CompletionStatus.WAITING_INPUT,
            waiting=True,
        )
        self.assertEqual(result.completion_status, CompletionStatus.WAITING_INPUT)
        self.assertEqual(result.missing_condition_ids, ("time-window",))
        self.assertEqual(supervisor.requests, [])

    async def test_research_insufficient_is_partial_with_warning(self) -> None:
        result, _ = await self._run(
            "industry_digest.research-insufficient/1",
            CompletionStatus.PARTIAL,
            frozenset({"RESEARCH_INSUFFICIENT"}),
        )
        self.assertEqual(result.completion_status, CompletionStatus.PARTIAL)
        self.assertIn("RESEARCH_INSUFFICIENT", result.warning_codes)


__all__ = ["IndustryDigestScenarioTests"]
