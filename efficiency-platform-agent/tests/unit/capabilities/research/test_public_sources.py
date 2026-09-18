from datetime import UTC, datetime

import pytest

from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchRequest,
    ResearchStatus,
)
from efficiency_platform_agent.capabilities.research.public_sources import (
    FreePublicResearchProvider,
    PublicResearchSource,
)
from efficiency_platform_agent.contracts.research_sources_v2 import (
    CandidateRecordV2,
    DiscoveryBatchV2,
    SourceAttemptV2,
    SourceUsageV2,
)


class _SourceProvider:
    def __init__(self, candidates: tuple[CandidateRecordV2, ...]) -> None:
        self.candidates = candidates
        self.calls = []

    async def discover(self, request):
        self.calls.append(request)
        now = datetime(2026, 9, 17, tzinfo=UTC)
        return DiscoveryBatchV2(
            request_id=request.request_id,
            candidates=self.candidates,
            completeness="complete",
            coverage="complete",
            attempts=(
                SourceAttemptV2(
                    attempt_id=f"attempt-{len(self.calls)}",
                    action_id=request.request_id,
                    source_id=request.source_id,
                    status="success" if self.candidates else "success_empty",
                    started_at=now,
                    finished_at=now,
                    returned_count=len(self.candidates),
                    filtered_count=0,
                    coverage="complete",
                    lease_id=request.lease_id,
                    usage=SourceUsageV2(
                        requests=1,
                        returned_items=len(self.candidates),
                        downloaded_bytes=100,
                    ),
                ),
            ),
        )


def _candidate(identifier: str, published_at: str, *, url: str | None = None):
    return CandidateRecordV2(
        candidate_id=f"candidate-{identifier}",
        source_id="official-feed",
        source_item_id=identifier,
        url=url or f"https://official.example/{identifier}",
        title=f"AI 推理优化进展 {identifier}",
        raw_published_at=published_at,
        timestamp_semantics="published",
        discovered_via="rss",
        content_scope="summary",
        inline_content="官方发布的大模型推理优化动态。",
    )


@pytest.mark.asyncio
async def test_provider_filters_exact_window_deduplicates_and_reports_shortage() -> None:
    source = _SourceProvider(
        (
            _candidate("inside", "2026-09-16T08:00:00+08:00"),
            _candidate("duplicate", "2026-09-16T09:00:00+08:00", url="https://official.example/inside"),
            _candidate("outside", "2026-09-15T08:00:00+08:00"),
        )
    )
    provider = FreePublicResearchProvider(
        sources=(PublicResearchSource("official-feed", "官方博客", True, source),),
        now=lambda: datetime(2026, 9, 17, 1, 30, tzinfo=UTC),
    )

    result = await provider.research(
        ResearchRequest(
            "research-request/1",
            "request-1",
            "task-1",
            "tenant-1",
            "严格给我3条2026年9月16日发生的AI行业新闻",
            None,
            3,
            ("goal",),
            "research-result/1",
        )
    )

    assert result.status is ResearchStatus.SUCCEEDED
    assert len(result.observations) == 1
    assert result.observations[0].published_at_epoch_ms == 1789520400000
    assert result.warnings == ("REQUESTED_SOURCE_COUNT_UNMET:1/3",)
    assert source.calls[0].time_window.original_text == "2026年9月16日"


@pytest.mark.asyncio
async def test_provider_skips_non_official_sources_when_user_requires_primary_sources() -> None:
    official = _SourceProvider((_candidate("official", "2026-09-16T08:00:00+08:00"),))
    discovery = _SourceProvider((_candidate("news", "2026-09-16T08:00:00+08:00"),))
    provider = FreePublicResearchProvider(
        sources=(
            PublicResearchSource("official-feed", "官方博客", True, official),
            PublicResearchSource("gdelt", "GDELT", False, discovery),
        ),
        now=lambda: datetime(2026, 9, 17, 1, 30, tzinfo=UTC),
    )

    await provider.research(
        ResearchRequest(
            "research-request/1",
            "request-2",
            "task-2",
            "tenant-1",
            "过去7天的大模型推理优化，只接受官方博客或论文主页",
            None,
            5,
            ("goal",),
            "research-result/1",
        )
    )

    assert len(official.calls) == 1
    assert discovery.calls == []


@pytest.mark.asyncio
async def test_provider_does_not_report_shortage_without_explicit_count() -> None:
    source = _SourceProvider((_candidate("one", "2026-09-16T08:00:00+08:00"),))
    provider = FreePublicResearchProvider(
        sources=(PublicResearchSource("official-feed", "官方博客", True, source),),
        now=lambda: datetime(2026, 9, 17, 1, 30, tzinfo=UTC),
    )

    result = await provider.research(
        ResearchRequest(
            "research-request/1",
            "request-3",
            "task-3",
            "tenant-1",
            "收集昨天的AI行业动态",
            None,
            5,
            ("goal",),
            "research-result/1",
        )
    )

    assert result.status is ResearchStatus.SUCCEEDED
    assert result.warnings == ()


@pytest.mark.asyncio
async def test_provider_filters_official_but_topic_irrelevant_candidates() -> None:
    relevant = _candidate("relevant", "2026-09-16T08:00:00+08:00")
    irrelevant = _candidate(
        "irrelevant", "2026-09-16T09:00:00+08:00"
    ).model_copy(
        update={
            "title": "AI for Societal Impact",
            "inline_content": "人工智能社会影响与教育普惠。",
        }
    )
    source = _SourceProvider((irrelevant, relevant))
    provider = FreePublicResearchProvider(
        sources=(PublicResearchSource("official-feed", "官方博客", True, source),),
        now=lambda: datetime(2026, 9, 17, 1, 30, tzinfo=UTC),
    )

    result = await provider.research(
        ResearchRequest(
            "research-request/1",
            "request-4",
            "task-4",
            "tenant-1",
            "过去7天内大模型推理优化的最新动态，只接受官方博客或论文主页",
            None,
            5,
            ("goal",),
            "research-result/1",
        )
    )

    assert [item.title for item in result.observations] == [relevant.title]


@pytest.mark.asyncio
async def test_zero_relevant_sources_is_successful_collection_with_explicit_warning() -> None:
    irrelevant = _candidate(
        "irrelevant-only", "2026-09-16T09:00:00+08:00"
    ).model_copy(
        update={
            "title": "AI for Societal Impact",
            "inline_content": "人工智能社会影响与教育普惠。",
        }
    )
    provider = FreePublicResearchProvider(
        sources=(
            PublicResearchSource(
                "official-feed", "官方博客", True, _SourceProvider((irrelevant,))
            ),
        ),
        now=lambda: datetime(2026, 9, 17, 1, 30, tzinfo=UTC),
    )

    result = await provider.research(
        ResearchRequest(
            "research-request/1",
            "request-5",
            "task-5",
            "tenant-1",
            "过去7天内大模型推理优化的最新动态",
            None,
            5,
            ("goal",),
            "research-result/1",
        )
    )

    assert result.status is ResearchStatus.EMPTY
    assert result.observations == ()
    assert "RESEARCH_SOURCES_UNAVAILABLE" in result.warnings
