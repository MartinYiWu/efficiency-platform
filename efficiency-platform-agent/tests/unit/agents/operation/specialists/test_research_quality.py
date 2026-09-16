"""研究 Specialist 与质量审校的离线单元测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    OperationQualityCheck,
    OperationQualityReport,
    QualityDimension,
    QualityStatus,
)
from efficiency_platform_agent.agents.operation.quality.evidence_gate import (
    EvidenceGate,
    EvidenceGatePolicy,
)
from efficiency_platform_agent.agents.operation.quality.revision import (
    RevisionAction,
    decide_revision,
)
from efficiency_platform_agent.agents.operation.specialists.contracts import (
    SpecialistExecutionResult,
)
from efficiency_platform_agent.agents.operation.specialists.quality import (
    QualityReviewAgent,
)
from efficiency_platform_agent.agents.operation.specialists.research import (
    ResearchInsightAgent,
)
from efficiency_platform_agent.agents.operation.specialists.runtime import (
    encode_specialist_result,
)
from efficiency_platform_agent.agents.operation.supervisor.dispatch import (
    SpecialistResultDecoder,
)
from efficiency_platform_agent.capabilities.research.contracts import ResearchRequest
from efficiency_platform_agent.core.multi_agent import BudgetUsage
from tests.contract.capabilities.test_research_provider_contract import (
    FixtureResearchProvider,
)


class ResearchQualitySpecialistTests(unittest.IsolatedAsyncioTestCase):
    """验证研究证据和有限修订边界。"""

    async def test_fixed_provider_observations_pass_evidence_gate(self) -> None:
        result = await FixtureResearchProvider().research(
            ResearchRequest(
                "research-request/1",
                "request-a",
                "task-a",
                "tenant-a",
                "收集行业信号",
                None,
                2,
                ("claim-1", "claim-2"),
                "research-result/1",
            )
        )
        pack = ResearchInsightAgent._evidence_pack("task-a", result.observations)
        decision = EvidenceGate().evaluate(
            pack,
            frozenset({"claim-1", "claim-2"}),
            EvidenceGatePolicy("research-v1", 2, 2, True, True),
        )
        self.assertTrue(decision.accepted)
        self.assertFalse(decision.source_content_verified)

    def test_quality_review_uses_existing_failed_status_for_revision(self) -> None:
        report = OperationQualityReport(
            "operation-quality-report/1",
            "quality-report-task-a",
            "task-a",
            ("deliverable-a",),
            (
                OperationQualityCheck(
                    QualityDimension.CONSISTENCY,
                    QualityStatus.FAILED,
                    ("deliverable-a",),
                    "需要修订",
                ),
            ),
            QualityStatus.FAILED,
            0,
        )
        decision = decide_revision(
            report,
            current_revision=0,
            max_revisions=2,
            revision_budget_available=True,
        )
        self.assertEqual(decision.action, RevisionAction.REVISE)
        self.assertIsNotNone(decision.request)
        self.assertIsInstance(QualityReviewAgent(), QualityReviewAgent)

    async def test_result_codec_preserves_full_evidence_pack(self) -> None:
        provider_result = await FixtureResearchProvider().research(
            ResearchRequest(
                "research-request/1",
                "request-a",
                "task-a",
                "tenant-a",
                "收集行业信号",
                None,
                2,
                ("claim-1", "claim-2"),
                "research-result/1",
            )
        )
        pack = ResearchInsightAgent._evidence_pack(
            "task-a", provider_result.observations
        )
        result = SpecialistExecutionResult(
            "operation-specialist-result/1",
            "task-a",
            ("research",),
            (),
            None,
            pack,
            None,
            (),
            (),
            None,
            None,
            None,
            BudgetUsage(iterations=1),
        )
        decoded = SpecialistResultDecoder().decode(
            encode_specialist_result(result, "run-a")
        )
        self.assertEqual(decoded.evidence_pack, pack)
        self.assertEqual(
            decoded.evidence_pack.records[1].duplicate_status,
            pack.records[1].duplicate_status,
        )

    async def test_result_codec_round_trips_deliverable_and_quality_report(
        self,
    ) -> None:
        """结果编解码必须无损保留非空交付物包和质量报告。"""
        provider_result = await FixtureResearchProvider().research(
            ResearchRequest(
                "research-request/1",
                "request-a",
                "task-a",
                "tenant-a",
                "收集行业信号",
                None,
                2,
                ("claim-1", "claim-2"),
                "research-result/1",
            )
        )
        pack = ResearchInsightAgent._evidence_pack(
            "task-a", provider_result.observations
        )
        bundle = ResearchInsightAgent._bundle("task-a", pack)
        report = OperationQualityReport(
            "operation-quality-report/1",
            "quality-report-task-a",
            "task-a",
            (bundle.deliverables[0].deliverable_id,),
            (
                OperationQualityCheck(
                    QualityDimension.COMPLETENESS,
                    QualityStatus.PASSED,
                    (),
                    "交付物字段完整",
                ),
            ),
            QualityStatus.PASSED,
            0,
        )
        result = SpecialistExecutionResult(
            "operation-specialist-result/1",
            "task-a",
            ("research",),
            (),
            bundle,
            pack,
            report,
            (),
            (),
            None,
            None,
            None,
            BudgetUsage(iterations=1),
        )

        decoded = SpecialistResultDecoder().decode(
            encode_specialist_result(result, "run-a")
        )

        self.assertEqual(decoded.deliverable_bundle, bundle)
        self.assertEqual(decoded.quality_report, report)


if __name__ == "__main__":
    unittest.main()
