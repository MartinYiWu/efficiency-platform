"""多平台内容场景包的离线回归测试。"""

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
        status: CompletionStatus,
        completed_scope: tuple[str, ...],
        missing_scope: tuple[str, ...],
        warnings=frozenset(),
    ):
        self.status, self.completed_scope, self.missing_scope, self.warnings = (
            status,
            completed_scope,
            missing_scope,
            warnings,
        )
        self.requests = []

    async def execute_scenario(self, request):
        self.requests.append(request)
        evidence = request.evidence_pack or build_empty_evidence_pack(
            request.task_spec.task_id
        )
        bundle = FakeS2OperationAssemblyPort().assemble(
            request.task_spec, request.operation_plan, evidence
        )
        return ScenarioExecutionResult(
            "multi_platform_content",
            "1.0.0",
            self.status,
            bundle,
            None,
            (),
            self.completed_scope,
            self.missing_scope,
            self.warnings,
            "SPECIALIST_PARTIAL_FAILURE"
            if self.status is CompletionStatus.PARTIAL
            else None,
        )


def _submission(sample_id: str, *, waiting: bool = False):
    submission = submission_from_sample(sample_by_id(sample_id))
    if waiting:
        submission = replace(
            submission,
            task_spec=replace(
                submission.task_spec,
                missing_critical_condition_ids=("platforms",),
                requires_user_input=True,
            ),
        )
    return submission


class MultiPlatformContentScenarioTests(IsolatedAsyncioTestCase):
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
            result = await ScenarioPackService(_Registry(), supervisor).run(submission)
        return result

    async def test_complete_has_three_independent_platform_scopes(self) -> None:
        scopes = (
            "platform-content-xiaohongshu",
            "platform-content-wechat-official-account",
            "platform-content-toutiao",
        )
        result = await self._run(
            "multi_platform_content.complete/1",
            _Supervisor(CompletionStatus.COMPLETE, scopes, ()),
        )
        self.assertEqual(result.completion_status, CompletionStatus.COMPLETE)
        self.assertEqual(result.completed_scope, scopes)

    async def test_missing_platforms_waits_without_supervisor_call(self) -> None:
        supervisor = _Supervisor(CompletionStatus.WAITING_INPUT, (), ("platforms",))
        result = await self._run(
            "multi_platform_content.waiting-platforms/1", supervisor, waiting=True
        )
        self.assertEqual(result.completion_status, CompletionStatus.WAITING_INPUT)
        self.assertEqual(supervisor.requests, [])

    async def test_toutiao_failure_preserves_two_platform_deliverables(self) -> None:
        scopes = (
            "platform-content-xiaohongshu",
            "platform-content-wechat-official-account",
        )
        result = await self._run(
            "multi_platform_content.toutiao-failed/1",
            _Supervisor(
                CompletionStatus.PARTIAL,
                scopes,
                ("platform-content-toutiao",),
                frozenset({"SPECIALIST_PARTIAL_FAILURE"}),
            ),
        )
        self.assertEqual(result.completion_status, CompletionStatus.PARTIAL)
        self.assertEqual(result.completed_scope, scopes)
        self.assertIn("platform-content-toutiao", result.missing_scope)


__all__ = ["MultiPlatformContentScenarioTests"]
