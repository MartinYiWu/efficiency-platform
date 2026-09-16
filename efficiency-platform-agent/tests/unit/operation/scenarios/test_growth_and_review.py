"""增长实验与运营复盘场景的服务级离线回归。"""

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
    """构造不访问外部系统的结构化复盘或实验交付物。"""

    deliverable = OperationDeliverable(
        "operation-deliverable/1",
        f"deliverable-{task_id}",
        DeliverableKind.ANALYSIS,
        "1.0.0",
        "离线运营分析",
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
    """按脚本返回固定结果并记录服务提交的 Supervisor 请求。"""

    def __init__(
        self,
        scenario_id: str,
        status: CompletionStatus,
        *,
        payload: JsonObject | None = None,
        warning_codes: frozenset[str] = frozenset(),
        error_code: str | None = None,
    ) -> None:
        self.scenario_id = scenario_id
        self.status = status
        self.payload = payload
        self.warning_codes = warning_codes
        self.error_code = error_code
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
            ("experiment-backlog",)
            if self.status is CompletionStatus.COMPLETE or bundle
            else (),
            ()
            if self.status is CompletionStatus.COMPLETE
            else (("actual-results",) if bundle else ()),
            self.warning_codes,
            self.error_code,
        )


def _submission(sample_id: str, *, waiting: bool = False):
    """把固定样本转换为生产入站并按场景补充等待条件。"""

    submission = submission_from_sample(sample_by_id(sample_id))
    if not waiting:
        return submission
    condition = {
        "growth_experiment": "funnel-stage",
        "operation_review": "metric-definition",
    }[submission.scenario_id]
    return replace(
        submission,
        task_spec=replace(
            submission.task_spec,
            missing_critical_condition_ids=(condition,),
            requires_user_input=True,
        ),
    )


class GrowthAndReviewServiceTests(IsolatedAsyncioTestCase):
    """验证增长和复盘场景实际经过 ScenarioPackService。"""

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

    async def test_growth_without_data_defines_experiments_but_not_actual_results(self):
        supervisor = _Supervisor(
            "growth_experiment",
            CompletionStatus.PARTIAL,
            payload=JsonObject(
                (
                    ("experiment_backlog", "已定义"),
                    ("baseline", "未验证"),
                )
            ),
            warning_codes=frozenset({"baseline-unverified"}),
            error_code="ANALYTICS_UNAVAILABLE",
        )
        result = await self._run(
            "growth_experiment.analytics-unavailable/1", supervisor
        )

        self.assertEqual(result.completion_status, CompletionStatus.PARTIAL)
        self.assertIn("baseline-unverified", result.warning_codes)
        self.assertIsNotNone(result.deliverable_bundle)
        payload = dict(result.deliverable_bundle.deliverables[0].payload.items)
        self.assertIn("experiment_backlog", payload)
        self.assertNotIn("actual-conversion", payload)

    async def test_review_unreadable_data_never_returns_analysis_claim(self):
        supervisor = _Supervisor(
            "operation_review",
            CompletionStatus.PARTIAL,
            warning_codes=frozenset({"DATA_UNREADABLE"}),
            error_code="DATA_UNREADABLE",
        )
        result = await self._run("operation_review.data-unreadable/1", supervisor)

        self.assertNotEqual(result.completion_status, CompletionStatus.COMPLETE)
        self.assertEqual(result.error_code, "DATA_UNREADABLE")
        self.assertIsNone(result.deliverable_bundle)

    async def test_review_complete_declares_scope_and_hypothesis_not_fact(self):
        supervisor = _Supervisor(
            "operation_review",
            CompletionStatus.COMPLETE,
            payload=JsonObject(
                (
                    ("data_definition", "已声明"),
                    ("time_window", "已声明"),
                    ("action_plan", "已声明"),
                    ("attribution_status", "hypothesis"),
                )
            ),
        )
        result = await self._run("operation_review.complete/1", supervisor)

        self.assertEqual(result.completion_status, CompletionStatus.COMPLETE)
        payload = dict(result.deliverable_bundle.deliverables[0].payload.items)
        self.assertTrue(
            {"data_definition", "time_window", "action_plan"} <= payload.keys()
        )
        self.assertEqual(payload["attribution_status"], "hypothesis")

    async def test_review_missing_metric_definition_waits_before_supervisor(self):
        supervisor = _Supervisor("operation_review", CompletionStatus.WAITING_INPUT)
        result = await self._run(
            "operation_review.waiting-metric-definition/1", supervisor, waiting=True
        )

        self.assertEqual(result.completion_status, CompletionStatus.WAITING_INPUT)
        self.assertEqual(result.missing_condition_ids, ("metric-definition",))
        self.assertEqual(supervisor.requests, [])


__all__ = ["GrowthAndReviewServiceTests"]
