"""基于免费 API、RSS/Atom 与公开网页元数据的研究 Provider。"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import urlsplit

from efficiency_platform_agent.agents.operation.contracts.evidence import (
    EvidenceDuplicateStatus,
    EvidenceQualityStatus,
    normalize_evidence_url,
)
from efficiency_platform_agent.agents.operation.contracts.task import SourceScope
from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchObservation,
    ResearchProviderPort,
    ResearchRequest,
    ResearchResult,
    ResearchStatus,
)
from efficiency_platform_agent.contracts.research_sources_v2 import (
    CandidateRecordV2,
    DiscoveryBatchV2,
    DiscoveryRequestV2,
    FetchedContentV2,
    FetchRequestV2,
)
from efficiency_platform_agent.contracts.research_transport_v2 import (
    ResearchUrlSourcePolicyV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.diagnostics import (
    DiagnosticRecorderPort,
    NoopDiagnosticRecorder,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.providers.research.arxiv import (
    ArxivConfig,
    ArxivProvider,
)
from efficiency_platform_agent.providers.research.feed import (
    FeedSourceConfig,
    FeedSourceProvider,
)
from efficiency_platform_agent.providers.research.gdelt import (
    GdeltConfig,
    GdeltProvider,
)
from efficiency_platform_agent.providers.research.hacker_news import (
    HackerNewsConfig,
    HackerNewsProvider,
)
from efficiency_platform_agent.providers.research.live_connector import (
    AsyncioPinnedHttpConnector,
    AsyncioTargetResolver,
)
from efficiency_platform_agent.providers.research.transport import (
    FetchLease,
    SafeHttpTransport,
)
from efficiency_platform_agent.security.url_policy import UrlPolicy

from .request_policy import (
    has_explicit_source_count,
    official_sources_only,
    resolve_research_window,
)


class _DiscoveryProvider(Protocol):
    async def discover(self, request: DiscoveryRequestV2) -> DiscoveryBatchV2: ...


@dataclass(frozen=True, slots=True)
class PublicResearchSource:
    """一个经过静态配置的免费公开来源。"""

    source_id: str
    publisher: str
    official: bool
    provider: _DiscoveryProvider


class _SafePublicFetcher:
    """只对适配器生成的固定 HTTPS 主机执行逐跳授权抓取。"""

    def __init__(self) -> None:
        self._resolver = AsyncioTargetResolver()
        self._transport = SafeHttpTransport(
            AsyncioPinnedHttpConnector(),
            url_policy=UrlPolicy(),
        )

    async def fetch(self, request: FetchRequestV2) -> FetchedContentV2:
        host = urlsplit(request.url).hostname
        if host is None:
            raise ValueError("PUBLIC_SOURCE_HOST_INVALID")
        return await self._transport.fetch(
            request,
            FetchLease(
                source_policy=ResearchUrlSourcePolicyV2(allowed_hosts=(host,)),
                resolver=self._resolver,
                remaining_budget=RemainingBudget(1, 4, 0, 0, 0, 20_000),
                max_wire_bytes=2 * 1024 * 1024,
                max_decoded_bytes=2 * 1024 * 1024,
                max_redirects=3,
                connect_timeout_seconds=3.0,
                request_timeout_seconds=20.0,
            ),
        )


class FreePublicResearchProvider(ResearchProviderPort):
    """按时间窗逐源采集、去重、过滤并投影为稳定研究观察。"""

    def __init__(
        self,
        *,
        sources: tuple[PublicResearchSource, ...] | None = None,
        now: Callable[[], datetime] | None = None,
        recorder: DiagnosticRecorderPort | None = None,
    ) -> None:
        self.now = now or (lambda: datetime.now(UTC))
        self.recorder = recorder or NoopDiagnosticRecorder()
        self.sources = sources or _default_sources()
        if not self.sources or len({item.source_id for item in self.sources}) != len(
            self.sources
        ):
            raise ValueError("PUBLIC_RESEARCH_SOURCES_INVALID")

    async def research(self, request: ResearchRequest) -> ResearchResult:
        if not isinstance(request, ResearchRequest):
            raise TypeError("request必须是ResearchRequest")
        anchor = self.now().astimezone(UTC)
        window = resolve_research_window(request.goal, now=anchor)
        allowed = tuple(
            source
            for source in self.sources
            if source.official or not official_sources_only(request.goal)
        )
        candidates: list[tuple[CandidateRecordV2, PublicResearchSource]] = []
        failures = 0
        discoveries = await asyncio.gather(
            *(self._discover(request, source, window) for source in allowed),
            return_exceptions=True,
        )
        for source, batch in zip(allowed, discoveries, strict=True):
            if isinstance(batch, asyncio.CancelledError):
                raise batch
            if isinstance(batch, BaseException):
                failures += 1
                continue
            if any(attempt.status == "failed" for attempt in batch.attempts):
                failures += 1
            candidates.extend((item, source) for item in batch.candidates)

        selected = _select(candidates, window.start, window.end, request.goal)[
            : request.max_sources
        ]
        if not selected:
            return ResearchResult(
                "research-result/1",
                request.request_id,
                request.task_id,
                request.tenant_id,
                ResearchStatus.EMPTY,
                (),
                (
                    "RESEARCH_SOURCES_UNAVAILABLE",
                    *(("PUBLIC_SOURCE_PARTIAL_FAILURE",) if failures else ()),
                ),
                None,
                UsageSnapshot(),
            )
        retrieved_at = int(anchor.timestamp() * 1_000)
        observations = tuple(
            _observation(
                request,
                candidate,
                source,
                retrieved_at=retrieved_at,
                start=window.start,
                end=window.end,
            )
            for candidate, source in selected
        )
        warnings = (
            (f"REQUESTED_SOURCE_COUNT_UNMET:{len(observations)}/{request.max_sources}",)
            if has_explicit_source_count(request.goal)
            and len(observations) < request.max_sources
            else ()
        )
        return ResearchResult(
            "research-result/1",
            request.request_id,
            request.task_id,
            request.tenant_id,
            ResearchStatus.SUCCEEDED,
            observations,
            warnings,
            None,
            UsageSnapshot(),
        )

    async def _discover(
        self,
        request: ResearchRequest,
        source: PublicResearchSource,
        window: ResolvedTimeWindow,
    ) -> DiscoveryBatchV2:
        digest = hashlib.sha256(
            f"{request.request_id}:{source.source_id}".encode()
        ).hexdigest()
        return await source.provider.discover(
            DiscoveryRequestV2(
                request_id=f"public-{digest[:24]}",
                source_id=source.source_id,
                tenant_id=request.tenant_id,
                run_id=f"research-{digest[:24]}",
                lease_id=f"lease-{digest[:24]}",
                authorization_scope_digest=digest,
                brief_digest=f"brief-{digest[:24]}",
                query=request.goal[:2_000],
                time_window=window,
                limit=min(100, max(12, request.max_sources * 4)),
            )
        )


def _default_sources() -> tuple[PublicResearchSource, ...]:
    fetcher = _SafePublicFetcher()
    return (
        PublicResearchSource(
            "google-ai-rss",
            "Google AI Blog",
            True,
            FeedSourceProvider(
                FeedSourceConfig(
                    "google-ai-rss",
                    "https://blog.google/technology/ai/rss/",
                    "latest_only",
                    "rss",
                ),
                fetcher,
            ),
        ),
        PublicResearchSource(
            "langgraph-releases",
            "LangGraph GitHub Releases",
            True,
            FeedSourceProvider(
                FeedSourceConfig(
                    "langgraph-releases",
                    "https://github.com/langchain-ai/langgraph/releases.atom",
                    "latest_only",
                    "atom",
                ),
                fetcher,
            ),
        ),
        PublicResearchSource(
            "arxiv-ai",
            "arXiv",
            True,
            ArxivProvider(
                ArxivConfig("arxiv-ai", categories=("cs.AI", "cs.LG")), fetcher
            ),
        ),
        PublicResearchSource(
            "gdelt-news",
            "GDELT",
            False,
            GdeltProvider(GdeltConfig("gdelt-news"), fetcher),
        ),
        PublicResearchSource(
            "hacker-news",
            "Hacker News",
            False,
            HackerNewsProvider(
                HackerNewsConfig("hacker-news", list_name="newstories", max_items=30),
                fetcher,
            ),
        ),
    )


def _select(
    values: list[tuple[CandidateRecordV2, PublicResearchSource]],
    start: datetime,
    end: datetime,
    goal: str,
) -> list[tuple[CandidateRecordV2, PublicResearchSource]]:
    selected: dict[str, tuple[CandidateRecordV2, PublicResearchSource, datetime]] = {}
    for candidate, source in values:
        if not _topic_relevant(goal, candidate):
            continue
        observed = _candidate_time(candidate)
        if observed is None or not start <= observed < end:
            continue
        try:
            url = normalize_evidence_url(candidate.url)
        except (TypeError, ValueError):
            continue
        current = selected.get(url)
        if current is None or observed > current[2]:
            selected[url] = (candidate, source, observed)
    ordered = sorted(selected.values(), key=lambda item: item[2], reverse=True)
    return [(candidate, source) for candidate, source, _ in ordered]


_INFERENCE_GOAL_TERMS = (
    "推理优化",
    "推理加速",
    "inference optimization",
    "inference acceleration",
    "llm inference",
    "model serving",
)
_INFERENCE_EVIDENCE_TERMS = (
    "推理",
    "inference",
    "serving",
    "量化",
    "quantization",
    "kv cache",
    "speculative decoding",
    "吞吐",
    "throughput",
    "latency",
    "vllm",
    "tensorrt",
    "flashinfer",
)
_AI_TERMS = ("人工智能", "大模型", "ai", "llm", "language model")


def _topic_relevant(goal: str, candidate: CandidateRecordV2) -> bool:
    """在证据入包前执行保守主题门禁，避免“官方但无关”冒充有效来源。"""

    normalized_goal = goal.casefold()
    text = f"{candidate.title}\n{candidate.inline_content}".casefold()
    if any(term in normalized_goal for term in _INFERENCE_GOAL_TERMS):
        return any(term in text for term in _AI_TERMS) and any(
            term in text for term in _INFERENCE_EVIDENCE_TERMS
        )
    if any(term in normalized_goal for term in _AI_TERMS):
        return any(term in text for term in _AI_TERMS)
    return True


def _candidate_time(candidate: CandidateRecordV2) -> datetime | None:
    value = (
        candidate.raw_published_at
        or candidate.raw_created_at
        or candidate.raw_updated_at
        or candidate.raw_first_seen_at
    )
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _observation(
    request: ResearchRequest,
    candidate: CandidateRecordV2,
    source: PublicResearchSource,
    *,
    retrieved_at: int,
    start: datetime,
    end: datetime,
) -> ResearchObservation:
    observed = _candidate_time(candidate)
    digest = hashlib.sha256(candidate.url.encode()).hexdigest()[:24]
    return ResearchObservation(
        observation_id=f"observation-{digest}",
        title=candidate.title,
        publisher=source.publisher,
        source_url=normalize_evidence_url(candidate.url),
        published_at_epoch_ms=(
            int(observed.timestamp() * 1_000) if observed is not None else None
        ),
        retrieved_at_epoch_ms=retrieved_at,
        source_scope=SourceScope.EXTERNAL_REFERENCE,
        supported_conclusion_ids=frozenset(request.expected_conclusion_ids),
        within_time_window=observed is not None and start <= observed < end,
        duplicate_status=EvidenceDuplicateStatus.UNIQUE,
        quality_status=EvidenceQualityStatus.VALID,
    )


__all__ = ["FreePublicResearchProvider", "PublicResearchSource"]
