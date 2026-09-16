"""S5A 研究与质量审校的离线端到端验收。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.quality.evidence_gate import (
    EvidenceGate,
    EvidenceGatePolicy,
)
from efficiency_platform_agent.agents.operation.specialists.quality import (
    QualityReviewAgent,
)
from efficiency_platform_agent.agents.operation.specialists.research import (
    ResearchInsightAgent,
)
from efficiency_platform_agent.capabilities.research.contracts import ResearchRequest
from tests.contract.capabilities.test_research_provider_contract import (
    FixtureResearchProvider,
)


class OperationResearchQualityAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    """验证固定研究样本可通过证据门禁并进入质量审校。"""

    async def test_fixed_research_sample_passes_gate_and_quality_review(self) -> None:
        provider = FixtureResearchProvider()
        request = ResearchRequest(
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
        result = await provider.research(request)
        evidence = ResearchInsightAgent._evidence_pack("task-a", result.observations)
        decision = EvidenceGate().evaluate(
            evidence,
            frozenset({"claim-1", "claim-2"}),
            EvidenceGatePolicy("research-v1", 2, 2, True, True),
        )
        self.assertTrue(decision.accepted)
        report, revision = QualityReviewAgent().review(
            ResearchInsightAgent._bundle("task-a", evidence)
        )
        self.assertEqual(report.final_status.value, "passed")
        self.assertEqual(revision.action.value, "accept")


if __name__ == "__main__":
    unittest.main()
