"""活动策划与内容日历场景的服务级离线回归。"""

from __future__ import annotations

from dataclasses import replace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    DeliverableBundle,
    DeliverableKind,
    GenerationProcessReference,
    OperationDeliverable,
)
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
from efficiency_platform_agent.core.run import JsonObject
from tests.support.s2_operation_fakes import (
    FakeS2OperationPlanningPort,
    build_context,
)
from tests.support.s6_scenario_fakes import RecordingFakeTool
from tests.support.s6_scenario_samples import sample_by_id, submission_from_sample


class _Registry:
    """提供固定 Manifest 的内存注册表。"""

    def __init__(self) -> None:
        self._items = {
            (manifest.scenario_id, manifest.semantic_version): manifest
            for manifest in build_s6_manifests()
        }

    def get(self, scenario_id: str, semantic_version: str):
        return self._items[(scenario_id, semantic_version)]


def _bundle(task_id: str, plan_id: str, payload: JsonObject) -> DeliverableBundle:
    """构造不访问外部系统的结构化场景交付物。"""

    deliverable = OperationDeliverable(
        "operation-deliverable/1",
        f"deliverable-{task_id}",
        DeliverableKind.PLAN,
        "1.0.0",
        "离线运营方案",
        (task_id,),
        (),
        None,
        payload,
        frozenset(),
        frozenset(),
        frozenset(),
        (),
        GenerationProcessReference(f"process-{task_id}", "operation-process/1", (), ()),
        None,
        None,
        plan_id,
        None,
        None,
    )
    return DeliverableBundle(
        "deliverable-bundle/1",
        f"bundle-{task_id}",
        task_id,
        plan_id,
        (deliverable,),
        None,
        (),
        frozenset(),
    )


class _Supervisor:
    """按测试脚本返回固定场景结果并记录请求。"""

    def __init__(
        self,
        scenario_id: str,
        status: CompletionStatus,
        *,
        payload: JsonObject | None = None,
        warning_codes: frozenset[str] = frozenset(),
        error_code: str | None = None,
        tool: RecordingFakeTool | None = None,
    ) -> None:
        self.scenario_id = scenario_id
        self.status = status
        self.payload = payload
        self.warning_codes = warning_codes
        self.error_code = error_code
        self.tool = tool
        self.requests = []

    async def execute_scenario(self, request):
        self.requests.append(request)
        bundle = (
            _bundle(
                request.task_spec.task_id, request.operation_plan.plan_id, self.payload
            )
            if self.payload is not None
            else None
        )
        return ScenarioExecutionResult(
            self.scenario_id,
            "1.0.0",
            self.status,
            bundle,
            None,
            (),
            ("campaign-strategy",)
            if self.status is CompletionStatus.COMPLETE or bundle
            else (),
            ()
            if self.status is CompletionStatus.COMPLETE
            else (("analysis",) if bundle else ()),
            self.warning_codes,
            self.error_code,
        )


def _submission(sample_id: str, *, waiting: bool = False):
    """把固定样本转换为生产入站并按场景补充等待条件。"""

    submission = submission_from_sample(sample_by_id(sample_id))
    if not waiting:
        return submission
    condition = {
        "campaign_plan": "campaign-window",
        "content_calendar": "calendar-window",
    }[submission.scenario_id]
    return replace(
        submission,
        task_spec=replace(
            submission.task_spec,
            missing_critical_condition_ids=(condition,),
            requires_user_input=True,
        ),
    )


class CampaignAndCalendarServiceTests(IsolatedAsyncioTestCase):
    """验证活动与日历场景实际经过 ScenarioPackService。"""

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

    async def test_campaign_complete_contains_schedule_board_risk_and_metrics(self):
        supervisor = _Supervisor(
            "campaign_plan",
            CompletionStatus.COMPLETE,
            payload=JsonObject(
                (
                    ("schedule", "已定义"),
                    ("task_board", "已定义"),
                    ("risk_register", "已定义"),
                    ("metric_definitions", "已定义"),
                )
            ),
        )
        result = await self._run("campaign_plan.complete/1", supervisor)

        self.assertEqual(result.completion_status, CompletionStatus.COMPLETE)
        self.assertIsNotNone(result.deliverable_bundle)
        payload = dict(result.deliverable_bundle.deliverables[0].payload.items)
        self.assertTrue(
            {"schedule", "task_board", "risk_register", "metric_definitions"}
            <= payload.keys()
        )
        self.assertEqual(len(supervisor.requests), 1)

    async def test_campaign_does_not_invoke_touch_tool(self):
        supervisor = _Supervisor(
            "campaign_plan",
            CompletionStatus.COMPLETE,
            payload=JsonObject((("schedule", "已定义"),)),
            tool=RecordingFakeTool(),
        )
        result = await self._run("campaign_plan.complete/1", supervisor)

        self.assertEqual(result.completion_status, CompletionStatus.COMPLETE)
        self.assertEqual(supervisor.tool.calls if supervisor.tool else (), [])

    async def test_calendar_profile_missing_fails_without_publication(self):
        supervisor = _Supervisor(
            "content_calendar",
            CompletionStatus.PARTIAL,
            warning_codes=frozenset({"PLATFORM_PROFILE_MISSING"}),
            error_code="PLATFORM_PROFILE_MISSING",
        )
        result = await self._run("content_calendar.profile-missing/1", supervisor)

        self.assertEqual(result.completion_status, CompletionStatus.FAILED)
        self.assertEqual(result.error_code, "PLATFORM_PROFILE_MISSING")
        self.assertIn("PLATFORM_PROFILE_MISSING", result.warning_codes)

    async def test_malformed_partial_result_fails_closed(self):
        supervisor = _Supervisor("campaign_plan", CompletionStatus.PARTIAL)
        result = await self._run("campaign_plan.growth-partial/1", supervisor)

        self.assertEqual(result.completion_status, CompletionStatus.FAILED)
        self.assertEqual(result.error_code, "SCENARIO_PARTIAL_INCOMPLETE")
        self.assertIsNone(result.deliverable_bundle)

    async def test_calendar_missing_range_waits_before_supervisor(self):
        supervisor = _Supervisor("content_calendar", CompletionStatus.WAITING_INPUT)
        result = await self._run(
            "content_calendar.waiting-calendar-range/1", supervisor, waiting=True
        )

        self.assertEqual(result.completion_status, CompletionStatus.WAITING_INPUT)
        self.assertEqual(result.missing_condition_ids, ("calendar-window",))
        self.assertEqual(supervisor.requests, [])


__all__ = ["CampaignAndCalendarServiceTests"]
