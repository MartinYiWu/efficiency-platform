"""质量审校后的有限修订决策测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    DeliverableBundle,
    DeliverableKind,
    GenerationProcessReference,
    OperationDeliverable,
    OperationQualityCheck,
    OperationQualityReport,
    QualityDimension,
    QualityStatus,
)
from efficiency_platform_agent.agents.operation.quality.revision import (
    RevisionAction,
    decide_revision,
)
from efficiency_platform_agent.agents.operation.specialists.quality import (
    QualityReviewAgent,
)
from efficiency_platform_agent.core.run import JsonObject


class RevisionDecisionTests(unittest.TestCase):
    """验证修订次数、预算不足和成功审校的稳定决策。"""

    def _report(self, status: QualityStatus) -> OperationQualityReport:
        return OperationQualityReport(
            "operation-quality-report/1",
            "report-a",
            "task-a",
            ("deliverable-a",),
            (
                OperationQualityCheck(
                    QualityDimension.CONSISTENCY, status, ("issue-a",), "结构存在冲突"
                ),
            ),
            status,
            0,
        )

    def test_third_revision_is_rejected_without_another_agent_call(self) -> None:
        decision = decide_revision(
            self._report(QualityStatus.FAILED),
            current_revision=2,
            max_revisions=2,
            revision_budget_available=True,
        )
        self.assertEqual(decision.action, RevisionAction.FAIL)
        self.assertEqual(decision.error_code, "QUALITY_NOT_MET")

    def test_budget_shortage_with_existing_report_is_partial(self) -> None:
        decision = decide_revision(
            self._report(QualityStatus.FAILED),
            current_revision=0,
            max_revisions=2,
            revision_budget_available=False,
        )
        self.assertEqual(decision.action, RevisionAction.PARTIAL)

    def test_passed_report_is_accepted_without_revision(self) -> None:
        decision = decide_revision(
            self._report(QualityStatus.PASSED),
            current_revision=0,
            max_revisions=2,
            revision_budget_available=True,
        )
        self.assertEqual(decision.action, RevisionAction.ACCEPT)
        self.assertIsNone(decision.request)

    def test_quality_agent_reports_cross_deliverable_conflict(self) -> None:
        deliverables = tuple(
            OperationDeliverable(
                "operation-deliverable/1",
                f"deliverable-{suffix}",
                DeliverableKind.COPY,
                "1.0.0",
                f"渠道文案-{suffix}",
                ("subject-a",),
                ("xhs",),
                None,
                JsonObject((("body", f"内容-{suffix}"),)),
                frozenset(),
                frozenset(),
                frozenset(),
                (),
                GenerationProcessReference(f"process-{suffix}", "1.0.0", (), ()),
                None,
                None,
                "plan-a",
                None,
                None,
            )
            for suffix in ("a", "b")
        )
        bundle = DeliverableBundle(
            "deliverable-bundle/1",
            "bundle-a",
            "task-a",
            "plan-a",
            deliverables,
            None,
            (),
            frozenset(),
        )
        report, decision = QualityReviewAgent().review(bundle)
        self.assertEqual(report.final_status, QualityStatus.FAILED)
        self.assertEqual(
            report.checks[0].issue_reference_ids, ("deliverable-a", "deliverable-b")
        )
        self.assertEqual(decision.action.value, "revise")


if __name__ == "__main__":
    unittest.main()
