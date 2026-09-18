"""免费来源真实研究矩阵 Runner 的离线契约。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from efficiency_platform_agent.contracts.live_acceptance_v2 import (
    LiveAcceptanceRequestV1,
)
from efficiency_platform_agent.contracts.research_sources_v2 import CandidateRecordV2
from efficiency_platform_agent.core.model import (
    ModelCandidate,
    ModelExecutionResult,
    ModelSelection,
    ModelTier,
)
from efficiency_platform_agent.core.run import (
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.harness.live_acceptance import (
    InMemoryLiveAcceptanceBudgetBinder,
    LiveAcceptanceAuthorization,
)
from efficiency_platform_agent.harness.live_research_v2 import (
    CollectedFreeSources,
    FreeSourceLiveAcceptanceRunner,
)


class FakeCollector:
    def __init__(self, items) -> None:
        self.items = items
        self.calls = 0

    async def collect(self, binding):
        self.calls += 1
        return CollectedFreeSources(self.items, ({"source_id": "free-feed", "status": "success"},))


class FakeRuntime:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, demand, request, *, remaining_budget, **kwargs):
        del remaining_budget, kwargs
        self.calls += 1
        payload = json.loads(request.messages[-1].content)
        items = [
            {"title": item["title"], "url": item["url"], "excerpt": "摘要"}
            for item in payload.get("sources", [])
        ]
        result = ProviderResult(
            request.contract_version,
            ProviderMessage(
                "assistant",
                json.dumps({"summary": "完成", "items": items}, ensure_ascii=False),
            ),
            ProviderUsage(100, 50, 0, 0, 0),
        )
        candidate = ModelCandidate(
            "candidate", "provider", "model", ModelTier.BALANCED, True, False, 64_000, True, False
        )
        return ModelExecutionResult(
            result,
            (ModelSelection(candidate, 1, None, "requested_tier"),),
            UsageSnapshot(100, 50, 0, False),
            False,
        )


def _binding():
    now = datetime.now(UTC)
    authorization = LiveAcceptanceAuthorization(
        "auth", "owner", now - timedelta(minutes=1), now + timedelta(hours=1),
        frozenset({"model_evaluation", "source_read"}),
        ("yesterday_ai", "exact_five", "ordinary_chat"),
        ("tenant",),
        1000,
    )
    request = LiveAcceptanceRequestV1(
        request_id="request", authorization_id="auth",
        case_ids=("yesterday_ai", "exact_five", "ordinary_chat"),
        requested_budget_microunits=1000,
    )
    return InMemoryLiveAcceptanceBudgetBinder().bind(
        authorization, request, tenant_id="tenant"
    )


def _item(index: int) -> CandidateRecordV2:
    return CandidateRecordV2(
        candidate_id=f"candidate-{index}",
        source_id="free-feed",
        source_item_id=str(index),
        url=f"https://example.com/{index}",
        title=f"AI news {index}",
        raw_published_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
        timestamp_semantics="published",
        discovered_via="rss",
    )


@pytest.mark.asyncio
async def test_runner_uses_real_source_candidates_and_validates_citations() -> None:
    collector = FakeCollector(tuple(_item(index) for index in range(5)))
    runtime = FakeRuntime()
    runner = FreeSourceLiveAcceptanceRunner(collector, runtime)

    result = await runner.run_case(
        "yesterday_ai", "收集昨天的 AI 行业动态并输出带来源摘要。", _binding()
    )

    assert result.status == "PASS"
    assert result.real_source_verified is True
    assert result.real_model_verified is True
    assert collector.calls == 1
    assert runtime.calls == 1
    assert runner.records[0]["citation_coverage"] == 1.0


@pytest.mark.asyncio
async def test_exact_five_is_partial_when_free_sources_have_only_two_items() -> None:
    runner = FreeSourceLiveAcceptanceRunner(
        FakeCollector((_item(1), _item(2))), FakeRuntime()
    )

    result = await runner.run_case(
        "exact_five", "收集昨天的 AI 行业动态，严格选 5 条；不足时明确说明。", _binding()
    )

    assert result.status == "PARTIAL"
    assert result.real_source_verified is True
    assert runner.records[0]["requested_count"] == 5
    assert runner.records[0]["delivered_count"] == 2


@pytest.mark.asyncio
async def test_empty_verified_window_is_partial_and_does_not_invent_facts() -> None:
    runner = FreeSourceLiveAcceptanceRunner(FakeCollector(()), FakeRuntime())

    result = await runner.run_case(
        "yesterday_ai", "收集昨天的 AI 行业动态并输出带来源摘要。", _binding()
    )

    assert result.status == "PARTIAL"
    assert result.real_source_verified is True
    assert runner.records[0]["delivered_count"] == 0
    assert runner.records[0]["citation_coverage"] == 1.0


@pytest.mark.asyncio
async def test_ordinary_chat_uses_model_without_claiming_source_verification() -> None:
    collector = FakeCollector((_item(1),))
    runner = FreeSourceLiveAcceptanceRunner(collector, FakeRuntime())

    result = await runner.run_case(
        "ordinary_chat", "你好，你叫什么名字？", _binding()
    )

    assert result.status == "PASS"
    assert result.real_model_verified is True
    assert result.real_source_verified is False
    assert collector.calls == 0
