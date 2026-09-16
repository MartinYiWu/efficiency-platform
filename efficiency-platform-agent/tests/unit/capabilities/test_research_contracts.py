"""研究 Provider 公共契约的离线约束测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.contracts.evidence import (
    EvidenceDuplicateStatus,
    EvidenceQualityStatus,
    TimeWindow,
)
from efficiency_platform_agent.agents.operation.contracts.task import SourceScope
from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchObservation,
    ResearchRequest,
    ResearchResult,
    ResearchStatus,
)


class ResearchContractsTests(unittest.TestCase):
    """验证研究请求、观察和结果的身份与版本字段。"""

    def test_request_has_frozen_versioned_identity(self) -> None:
        request = ResearchRequest(
            "research-request/1",
            "request-a",
            "task-a",
            "tenant-a",
            "收集行业信号",
            TimeWindow(1780000000000, 1780100000000),
            2,
            ("claim-1", "claim-2"),
            "research-result/1",
        )
        self.assertEqual(
            (
                request.contract_version,
                request.request_id,
                request.result_schema_version,
            ),
            ("research-request/1", "request-a", "research-result/1"),
        )
        with self.assertRaises((AttributeError, TypeError)):
            request.request_id = "request-b"  # type: ignore[misc]

    def test_observation_contains_typed_source_and_claim_fields(self) -> None:
        observation = ResearchObservation(
            "observation-1",
            "算力基础设施投资持续增长",
            "示例产业研究院",
            "https://example.com/industry/compute-investment",
            1780000000000,
            1780003600000,
            SourceScope.EXTERNAL_REFERENCE,
            frozenset({"claim-1"}),
            True,
            EvidenceDuplicateStatus.UNIQUE,
            EvidenceQualityStatus.VALID,
        )
        self.assertEqual(observation.supported_conclusion_ids, frozenset({"claim-1"}))

    def test_failed_result_is_typed_without_observations(self) -> None:
        result = ResearchResult(
            "research-result/1",
            "request-a",
            "task-a",
            "tenant-a",
            ResearchStatus.FAILED,
            (),
            ("研究 Provider 不可用",),
            "RESEARCH_UNAVAILABLE",
        )
        self.assertEqual(result.error_code, "RESEARCH_UNAVAILABLE")
        self.assertEqual(result.observations, ())


if __name__ == "__main__":
    unittest.main()
