"""X04 免费公开来源真实链路的受控验收执行器。"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Literal, Protocol, runtime_checkable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from efficiency_platform_agent.capabilities.model.runtime import ModelLeaseContext
from efficiency_platform_agent.contracts.live_acceptance_v2 import (
    LiveAcceptanceCaseResultV1,
)
from efficiency_platform_agent.contracts.research_sources_v2 import (
    CandidateRecordV2,
    DiscoveryRequestV2,
    FetchedContentV2,
    FetchRequestV2,
)
from efficiency_platform_agent.contracts.research_transport_v2 import (
    ResearchUrlSourcePolicyV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.budget_execution import BudgetExecutionBinding
from efficiency_platform_agent.core.model import (
    ModelDemand,
    ModelExecutionResult,
    ModelTier,
)
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.providers.research.feed import (
    FeedSourceConfig,
    FeedSourceProvider,
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
    HttpBudgetContext,
    SafeHttpTransport,
)
from efficiency_platform_agent.security.url_policy import UrlPolicy


@dataclass(frozen=True, slots=True)
class CollectedFreeSources:
    candidates: tuple[CandidateRecordV2, ...]
    attempts: tuple[dict[str, object], ...]


@runtime_checkable
class FreeSourceCollector(Protocol):
    async def collect(
        self, binding: BudgetExecutionBinding
    ) -> CollectedFreeSources: ...


class _BoundSafeFetcher:
    def __init__(self, binding: BudgetExecutionBinding) -> None:
        self.binding = binding
        self.resolver = AsyncioTargetResolver()
        self.transport = SafeHttpTransport(
            AsyncioPinnedHttpConnector(),
            url_policy=UrlPolicy(),
        )

    async def fetch(self, request: FetchRequestV2) -> FetchedContentV2:
        host = urlsplit(request.url).hostname
        if host is None:
            raise ValueError("LIVE_SOURCE_HOST_INVALID")
        prefix, version = await self.binding.next_invocation("source")
        context = HttpBudgetContext(
            self.binding.port,
            self.binding.scope,
            prefix,
            version,
        )
        try:
            return await self.transport.fetch(
                request,
                FetchLease(
                    source_policy=ResearchUrlSourcePolicyV2(
                        allowed_hosts=(host,)
                    ),
                    resolver=self.resolver,
                    remaining_budget=RemainingBudget(
                        1,
                        4,
                        0,
                        0,
                        0,
                        15_000,
                    ),
                    max_wire_bytes=2 * 1024 * 1024,
                    max_decoded_bytes=2 * 1024 * 1024,
                    max_redirects=3,
                    connect_timeout_seconds=3.0,
                    request_timeout_seconds=15.0,
                    budget_context=context,
                ),
            )
        finally:
            self.binding.update_version(context.version)


class LiveFreeSourceCollector:
    """通过安全固定 IP 传输读取两个 Feed 和 HN 公共 API。"""

    def __init__(self) -> None:
        self._cached: CollectedFreeSources | None = None
        self.collection_count = 0
        self.cache_hit_count = 0

    async def collect(
        self, binding: BudgetExecutionBinding
    ) -> CollectedFreeSources:
        if self._cached is not None:
            self.cache_hit_count += 1
            return self._cached
        self.collection_count += 1
        fetcher = _BoundSafeFetcher(binding)
        now = datetime.now(UTC)
        window = ResolvedTimeWindow(
            start=now - timedelta(days=14),
            end=now + timedelta(minutes=1),
            timezone="Asia/Shanghai",
            precision="exact",
            original_text="最近14天验收发现窗口",
            anchor=now,
        )
        providers = (
            FeedSourceProvider(
                FeedSourceConfig(
                    "fixture_official_feed",
                    "https://blog.google/rss/",
                    "latest_only",
                    "rss",
                ),
                fetcher,
            ),
            FeedSourceProvider(
                FeedSourceConfig(
                    "fixture_github_releases",
                    "https://github.com/langchain-ai/langgraph/releases.atom",
                    "latest_only",
                    "atom",
                ),
                fetcher,
            ),
            HackerNewsProvider(
                HackerNewsConfig(
                    "fixture_hacker_news",
                    max_concurrency=1,
                    max_items=12,
                ),
                fetcher,
            ),
        )
        candidates: list[CandidateRecordV2] = []
        attempts: list[dict[str, object]] = []
        for provider in providers:
            source_id = provider.config.source_id
            digest = hashlib.sha256(source_id.encode()).hexdigest()[:16]
            batch = await provider.discover(
                DiscoveryRequestV2(
                    request_id=f"x04-live-{digest}",
                    source_id=source_id,
                    tenant_id=binding.scope.tenant_id,
                    run_id=binding.scope.run_id,
                    lease_id=binding.lease_id,
                    authorization_scope_digest=binding.authorization_scope_digest,
                    brief_digest=f"x04-live-brief-{digest}",
                    query="AI 大模型 推理优化",
                    time_window=window,
                    limit=12,
                )
            )
            candidates.extend(batch.candidates)
            attempts.extend(item.model_dump(mode="json") for item in batch.attempts)
        deduplicated = {
            candidate.url: candidate for candidate in candidates
        }
        self._cached = CollectedFreeSources(
            tuple(deduplicated.values()), tuple(attempts)
        )
        return self._cached


class FreeSourceLiveAcceptanceRunner:
    """五类真实请求的统一 Runner；模型不能发明来源 URL。"""

    def __init__(self, collector: FreeSourceCollector, runtime: Any) -> None:
        if not isinstance(collector, FreeSourceCollector):
            raise TypeError("LIVE_SOURCE_COLLECTOR_INVALID")
        if not callable(getattr(runtime, "complete", None)):
            raise TypeError("LIVE_MODEL_RUNTIME_INVALID")
        self.collector = collector
        self.runtime = runtime
        self.records: list[dict[str, object]] = []
        self._last_sources: tuple[CandidateRecordV2, ...] = ()

    async def run_case(
        self,
        case_id: str,
        prompt: str,
        binding: BudgetExecutionBinding,
    ) -> LiveAcceptanceCaseResultV1:
        started = time.monotonic()
        window = _case_window(case_id)
        attempts: tuple[dict[str, object], ...] = ()
        if case_id == "ordinary_chat":
            sources: tuple[CandidateRecordV2, ...] = ()
        elif case_id == "rewrite_wechat":
            sources = self._last_sources
        else:
            collected = await self.collector.collect(binding)
            attempts = collected.attempts
            sources = _select_sources(collected.candidates, case_id, window)
            if sources:
                self._last_sources = sources
        requested_count = 5 if case_id == "exact_five" else None
        maximum = requested_count or 8
        sources = sources[:maximum]
        execution = await self._invoke_model(case_id, prompt, sources, binding)
        output, citation_coverage = _validated_output(execution, sources, case_id)
        model_verified = bool(
            execution.result.error is None
            and (execution.usage.input_tokens > 0 or execution.usage.output_tokens > 0)
        )
        source_required = case_id != "ordinary_chat"
        source_access_verified = bool(attempts) and all(
            item.get("status") != "failed" for item in attempts
        )
        source_verified = citation_coverage == 1.0 and (
            bool(sources) or source_access_verified
        )
        delivered_count = len(output.get("items", ()))
        status: Literal["PASS", "PARTIAL", "FAILED"]
        if not model_verified or (source_required and not source_verified):
            status = "FAILED"
        elif (source_required and not sources) or (
            requested_count is not None and delivered_count < requested_count
        ):
            status = "PARTIAL"
        else:
            status = "PASS"
        run_digest = hashlib.sha256(
            f"{binding.lease_id}:{case_id}:{len(self.records)}".encode()
        ).hexdigest()[:24]
        self.records.append(
            {
                "case_id": case_id,
                "status": status,
                "resolved_window": window,
                "source_attempts": list(attempts),
                "sources": [
                    {
                        "source_id": item.source_id,
                        "title": item.title,
                        "url": item.url,
                        "published_at": item.raw_published_at
                        or item.raw_updated_at,
                    }
                    for item in sources
                ],
                "requested_count": requested_count,
                "delivered_count": delivered_count,
                "citation_coverage": citation_coverage,
                "model_usage": {
                    "input_tokens": execution.usage.input_tokens,
                    "output_tokens": execution.usage.output_tokens,
                    "cost_microunits": execution.usage.cost_microunits,
                    "cost_observed": execution.usage.cost_microunits > 0,
                },
                "latency_ms": max(0, int((time.monotonic() - started) * 1000)),
                "output": output,
            }
        )
        return LiveAcceptanceCaseResultV1(
            case_id=case_id,
            status=status,
            run_id=f"live-case-{run_digest}",
            real_model_verified=model_verified,
            real_source_verified=source_verified,
        )

    async def _invoke_model(
        self,
        case_id: str,
        prompt: str,
        sources: tuple[CandidateRecordV2, ...],
        binding: BudgetExecutionBinding,
    ) -> ModelExecutionResult:
        payload = json.dumps(
            {
                "case_id": case_id,
                "request": prompt,
                "sources": [
                    {
                        "title": item.title,
                        "url": item.url,
                        "published_at": item.raw_published_at
                        or item.raw_updated_at,
                        "excerpt": (item.inline_content or "")[:800],
                    }
                    for item in sources
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        snapshot = await binding.port.snapshot(binding.scope)
        remaining = RemainingBudget(
            max(1, snapshot.limits.max_calls - snapshot.used.calls),
            max(1, snapshot.limits.max_calls - snapshot.used.calls),
            max(1, snapshot.limits.max_input_tokens - snapshot.used.input_tokens),
            max(1, snapshot.limits.max_output_tokens - snapshot.used.output_tokens),
            max(
                1,
                snapshot.limits.max_cost_microunits
                - snapshot.used.cost_microunits,
            ),
            max(
                1,
                (snapshot.limits.deadline_epoch_ms or int(time.time() * 1000) + 120_000)
                - int(time.time() * 1000),
            ),
        )
        prefix, version = await binding.next_invocation("model")
        lease = ModelLeaseContext(
            binding.port,
            binding.scope,
            prefix,
            version,
            reserve_cost_microunits=0,
        )
        result = await self.runtime.complete(
            ModelDemand(
                "research-v2-live-acceptance/1",
                ModelTier.BALANCED,
                True,
                False,
                max(1, len(payload) // 4),
                4_000,
            ),
            ProviderRequest(
                "research-v2-live-acceptance/1",
                (
                    ProviderMessage(
                        "system",
                        "只输出JSON对象，格式为summary字符串和items数组；每个item只含title、url、excerpt。"
                        "只能依据给定sources，不得新增URL；来源不足必须在summary明确说明。普通聊天items为空。",
                    ),
                    ProviderMessage("user", payload),
                ),
                JsonObject(
                    (
                        ("temperature", 0),
                        (
                            "response_format",
                            JsonObject((("type", "json_object"),)),
                        ),
                    )
                ),
                min(120_000, remaining.timeout_ms),
            ),
            remaining_budget=remaining,
            lease_context=lease,
        )
        binding.update_version(lease.version)
        return result


def _case_window(case_id: str) -> dict[str, str] | None:
    if case_id in {"ordinary_chat", "rewrite_wechat"}:
        return None
    zone = ZoneInfo("Asia/Shanghai")
    local_now = datetime.now(zone)
    if case_id in {"yesterday_ai", "exact_five"}:
        end_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_local = end_local - timedelta(days=1)
        label = "昨天"
    else:
        current_week = (
            local_now - timedelta(days=local_now.weekday())
        ).replace(hour=0, minute=0, second=0, microsecond=0)
        start_local = current_week - timedelta(days=7)
        end_local = current_week
        label = "上周"
    return {
        "label": label,
        "start": start_local.astimezone(UTC).isoformat(),
        "end": end_local.astimezone(UTC).isoformat(),
        "timezone": "Asia/Shanghai",
    }


def _select_sources(
    candidates: tuple[CandidateRecordV2, ...],
    case_id: str,
    window: dict[str, str] | None,
) -> tuple[CandidateRecordV2, ...]:
    if window is None:
        return candidates
    start = datetime.fromisoformat(window["start"])
    end = datetime.fromisoformat(window["end"])
    selected: list[CandidateRecordV2] = []
    for item in candidates:
        observed = _candidate_time(item)
        if observed is None or not start <= observed < end:
            continue
        searchable = f"{item.title} {item.inline_content or ''}".lower()
        if case_id == "last_week_topic":
            relevant = any(
                token in searchable
                for token in ("inference", "reasoning", "llm", "model", "推理", "模型")
            )
        else:
            relevant = any(
                token in searchable
                for token in ("ai", "artificial intelligence", "llm", "model", "人工智能", "大模型")
            )
        if relevant:
            selected.append(item)
    selected.sort(key=lambda item: _candidate_time(item) or datetime.min.replace(tzinfo=UTC), reverse=True)
    return tuple(selected)


def _candidate_time(item: CandidateRecordV2) -> datetime | None:
    value = item.raw_published_at or item.raw_updated_at
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _validated_output(
    execution: ModelExecutionResult,
    sources: tuple[CandidateRecordV2, ...],
    case_id: str,
) -> tuple[dict[str, Any], float]:
    if execution.result.error is not None or execution.result.message is None:
        return {"summary": "模型调用失败", "items": []}, 0.0
    try:
        content = execution.result.message.content
        if not isinstance(content, str):
            raise TypeError
        decoded = json.loads(content)
        if not isinstance(decoded, dict) or not isinstance(decoded.get("summary"), str):
            raise TypeError
        items = decoded.get("items")
        if not isinstance(items, list):
            raise TypeError
        allowed = {item.url for item in sources}
        validated = []
        for item in items:
            if not isinstance(item, dict) or set(item) != {"title", "url", "excerpt"}:
                raise TypeError
            if not all(isinstance(item[key], str) for key in item):
                raise TypeError
            if item["url"] not in allowed:
                raise ValueError
            validated.append(item)
        if case_id == "ordinary_chat" and validated:
            raise ValueError
        return {"summary": decoded["summary"], "items": validated}, (
            1.0 if not validated or all(item["url"] in allowed for item in validated) else 0.0
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"summary": "模型输出未通过引用校验", "items": []}, 0.0


__all__ = [
    "CollectedFreeSources",
    "FreeSourceLiveAcceptanceRunner",
    "LiveFreeSourceCollector",
]
