"""Supervisor 结果聚合、部分失败与修订裁决测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.contracts.evidence import (
    ConclusionSupport,
    EvidenceDuplicateStatus,
    EvidencePack,
    EvidenceQualityStatus,
    EvidenceRecord,
)
from efficiency_platform_agent.agents.operation.contracts.task import SourceScope
from efficiency_platform_agent.agents.operation.supervisor.aggregation import (
    ResultAggregator,
    RevisionDecision,
)
from efficiency_platform_agent.agents.operation.supervisor.dispatch import (
    SpecialistResultEnvelope,
)
from efficiency_platform_agent.core.agent import CapabilityRequirement
from efficiency_platform_agent.core.multi_agent import (
    BudgetUsage,
    CompletionStatus,
    TaskExecutionStatus,
    TaskFailureMode,
    TaskGraph,
    TaskNode,
    TaskOutcome,
)
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject


def _node(
    task_id: str, *, required: bool = True, depends_on: tuple[str, ...] = ()
) -> TaskNode:
    return TaskNode(
        task_id=task_id,
        task_type=f"synthetic.{task_id}",
        capability_requirement=CapabilityRequirement(
            all_of=frozenset({f"synthetic.{task_id}"})
        ),
        input_schema_version="synthetic-input/1",
        output_schema_version="synthetic-output/1",
        depends_on=depends_on,
        required=required,
        failure_mode=(
            TaskFailureMode.FAIL_PLAN if required else TaskFailureMode.SKIP_WITH_WARNING
        ),
        input_reference_ids=(),
        context_view=JsonObject(),
        allowed_tools=frozenset(),
        required_permissions=frozenset(),
        requested_budget=ExecutionBudget(2, 1, 10, 10, 1000, 0),
        expected_deliverable_ids=(f"deliverable-{task_id}",),
        quality_check_ids=frozenset(),
    )


def _graph(*nodes: TaskNode) -> TaskGraph:
    return TaskGraph(
        plan_id="plan-a",
        plan_contract_version="operation-plan/1",
        plan_revision=0,
        tasks=tuple(nodes),
        topological_order=tuple(node.task_id for node in nodes),
    )


def _outcome(task_id: str, status: TaskExecutionStatus) -> TaskOutcome:
    return TaskOutcome(
        task_id=task_id,
        agent_id="specialist-a",
        status=status,
        result=JsonObject((("task_id", task_id),))
        if status is TaskExecutionStatus.SUCCEEDED
        else None,
        error_code=None
        if status is TaskExecutionStatus.SUCCEEDED
        else f"{status.value.upper()}_ERROR",
        completed_scope=(f"scope-{task_id}",)
        if status is TaskExecutionStatus.SUCCEEDED
        else (),
        missing_scope=()
        if status is TaskExecutionStatus.SUCCEEDED
        else (f"scope-{task_id}",),
        trusted_usage=BudgetUsage(),
        attempt=1,
        revision=0,
        fence_token=1,
    )


def _evidence_pack(task_id: str) -> EvidencePack:
    record = EvidenceRecord(
        evidence_id="evidence-shared",
        title="合成来源",
        publisher="合成发布者",
        source_url="https://example.test/source",
        published_at_epoch_ms=1,
        retrieved_at_epoch_ms=2,
        source_scope=SourceScope.EXTERNAL_REFERENCE,
        supported_conclusion_ids=frozenset({"conclusion-a"}),
        within_time_window=True,
        duplicate_status=EvidenceDuplicateStatus.UNIQUE,
        quality_status=EvidenceQualityStatus.UNVERIFIED,
    )
    return EvidencePack(
        contract_version="evidence-pack/1",
        pack_id=f"pack-{task_id}",
        task_id=task_id,
        records=(record,),
        supports=(ConclusionSupport("conclusion-a", frozenset({"evidence-shared"})),),
    )


def _envelope(task_id: str) -> SpecialistResultEnvelope:
    return SpecialistResultEnvelope(
        contract_version="operation-specialist-result/1",
        task_id=task_id,
        completed_scope=(),
        missing_scope=(),
        deliverable_bundle=None,
        evidence_pack=_evidence_pack(task_id),
        quality_report=None,
        assumptions=(),
        warnings=(),
        error_code=None,
        requested_capability=None,
        revision_request=None,
        usage=None,
    )


class AggregationTest(unittest.TestCase):
    """验证结果状态、范围和失败信息不会被静默覆盖。"""

    def test_all_success_is_complete_with_completed_scope(self) -> None:
        result = ResultAggregator().aggregate(
            _graph(_node("a"), _node("b")),
            (
                _outcome("a", TaskExecutionStatus.SUCCEEDED),
                _outcome("b", TaskExecutionStatus.SUCCEEDED),
            ),
        )
        self.assertEqual(result.completion_status, CompletionStatus.COMPLETE)
        self.assertEqual(result.completed_scope, ("scope-a", "scope-b"))
        self.assertEqual(result.missing_scope, ())

    def test_optional_failure_is_partial_not_complete(self) -> None:
        result = ResultAggregator().aggregate(
            _graph(_node("required"), _node("optional", required=False)),
            (
                _outcome("required", TaskExecutionStatus.SUCCEEDED),
                _outcome("optional", TaskExecutionStatus.FAILED),
            ),
        )
        self.assertEqual(result.completion_status, CompletionStatus.PARTIAL)
        self.assertIn("scope-optional", result.missing_scope)
        self.assertTrue(result.failures)

    def test_required_failure_is_failed_and_cancelled_is_terminal(self) -> None:
        failed = ResultAggregator().aggregate(
            _graph(_node("required")),
            (_outcome("required", TaskExecutionStatus.FAILED),),
        )
        self.assertEqual(failed.completion_status, CompletionStatus.FAILED)
        cancelled = ResultAggregator().aggregate(
            _graph(_node("required")),
            (_outcome("required", TaskExecutionStatus.CANCELLED),),
        )
        self.assertEqual(cancelled.completion_status, CompletionStatus.CANCELLED)

    def test_dependency_skip_enters_missing_scope(self) -> None:
        result = ResultAggregator().aggregate(
            _graph(
                _node("prepare", required=False),
                _node("compose", depends_on=("prepare",)),
            ),
            (
                _outcome("prepare", TaskExecutionStatus.SKIPPED),
                _outcome("compose", TaskExecutionStatus.SUCCEEDED),
            ),
        )
        self.assertIn("scope-prepare", result.missing_scope)
        self.assertIn("compose", result.missing_scope)

    def test_revision_is_rejected_at_limit_or_task_limit(self) -> None:
        allowed = RevisionDecision.decide(
            revision=1, max_revisions=2, remaining_budget=True
        )
        self.assertTrue(allowed.allowed)
        denied = RevisionDecision.decide(
            revision=2, max_revisions=2, remaining_budget=True
        )
        self.assertFalse(denied.allowed)
        too_many = RevisionDecision.decide(
            revision=0,
            max_revisions=2,
            remaining_budget=True,
            current_task_count=16,
            requested_task_count=1,
        )
        self.assertFalse(too_many.allowed)

    def test_evidence_records_are_preserved_and_duplicate_is_explicit(self) -> None:
        result = ResultAggregator().aggregate(
            _graph(_node("a"), _node("b")),
            (
                _outcome("a", TaskExecutionStatus.SUCCEEDED),
                _outcome("b", TaskExecutionStatus.SUCCEEDED),
            ),
            (_envelope("a"), _envelope("b")),
        )
        self.assertIsNotNone(result.evidence_pack)
        self.assertEqual(len(result.evidence_pack.records), 2)  # type: ignore[union-attr]
        self.assertIn("evidence:evidence-shared", result.conflicts)


if __name__ == "__main__":
    unittest.main()
