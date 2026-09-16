"""供 S5 Fake 与 S7 真实适配器共用的研究 Provider 契约测试。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from efficiency_platform_agent.agents.operation.contracts.evidence import (
    EvidenceDuplicateStatus,
    EvidenceQualityStatus,
)
from efficiency_platform_agent.agents.operation.contracts.task import SourceScope
from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchObservation,
    ResearchProviderPort,
    ResearchRequest,
    ResearchResult,
    ResearchStatus,
)

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "operation"
    / "research"
    / "industry_signal_v1.json"
)


class FixtureResearchProvider:
    """只从版本化固定 JSON 样本返回结果，不执行网络访问。"""

    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.calls: list[ResearchRequest] = []

    async def research(self, request: ResearchRequest) -> ResearchResult:
        self.calls.append(request)
        if self.unavailable:
            return ResearchResult(
                "research-result/1",
                request.request_id,
                request.task_id,
                request.tenant_id,
                ResearchStatus.FAILED,
                (),
                ("固定样本 Provider 已禁用",),
                "RESEARCH_UNAVAILABLE",
            )
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        observations = tuple(
            ResearchObservation(
                item["observation_id"],
                item["title"],
                item["publisher"],
                item["source_url"],
                item["published_at_epoch_ms"],
                item["retrieved_at_epoch_ms"],
                SourceScope(item["source_scope"]),
                frozenset(item["supported_conclusion_ids"]),
                item["within_time_window"],
                EvidenceDuplicateStatus(item["duplicate_status"]),
                EvidenceQualityStatus(item["quality_status"]),
            )
            for item in payload["observations"][: request.max_sources]
        )
        return ResearchResult(
            "research-result/1",
            request.request_id,
            request.task_id,
            request.tenant_id,
            ResearchStatus.SUCCEEDED,
            observations,
            (),
            None,
        )


class ResearchProviderContractTests(unittest.IsolatedAsyncioTestCase):
    """验证 S7 适配器必须遵循单一研究端口。"""

    def _request(self) -> ResearchRequest:
        return ResearchRequest(
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

    async def test_fixture_preserves_request_identity_and_result_version(self) -> None:
        provider = FixtureResearchProvider()
        request = self._request()
        result = await provider.research(request)
        self.assertIsInstance(provider, ResearchProviderPort)
        self.assertEqual(result.contract_version, "research-result/1")
        self.assertEqual(
            (result.request_id, result.task_id, result.tenant_id),
            (request.request_id, request.task_id, request.tenant_id),
        )
        self.assertEqual(len(result.observations), 2)
        self.assertEqual(
            {item.publisher for item in result.observations},
            {"示例产业研究院", "示例数据观察站"},
        )

    async def test_unavailable_provider_returns_typed_failure_without_payload(
        self,
    ) -> None:
        result = await FixtureResearchProvider(unavailable=True).research(
            self._request()
        )
        self.assertEqual(
            (result.status, result.error_code),
            (ResearchStatus.FAILED, "RESEARCH_UNAVAILABLE"),
        )
        self.assertEqual(result.observations, ())
        self.assertFalse(hasattr(result, "raw_response"))


if __name__ == "__main__":
    unittest.main()
