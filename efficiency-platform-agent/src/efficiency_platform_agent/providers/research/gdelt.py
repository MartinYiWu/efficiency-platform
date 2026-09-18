"""GDELT DOC API 的只读 URL 线索适配器。"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, urlencode, urlsplit

from efficiency_platform_agent.contracts.research_sources_v2 import (
    CandidateRecordV2,
    DiscoveryBatchV2,
    DiscoveryRequestV2,
    FetchRequestV2,
)

from ._adapter_support import (
    AdapterDataError,
    AttemptStatus,
    ResearchDocumentFetcher,
    as_mapping,
    as_nonblank,
    candidate_id,
    error_downloaded_bytes,
    error_http_status,
    error_request_count,
    exception_error_code,
    make_attempt,
    nonnegative_error_header_int,
    nonnegative_header_int,
    now_utc,
    parse_json,
    validate_source_request,
)


@dataclass(frozen=True, slots=True)
class GdeltConfig:
    source_id: str
    earliest_supported_at: datetime | None = None
    api_origin: str = "https://api.gdeltproject.org"

    def __post_init__(self) -> None:
        if not self.source_id.strip() or self.api_origin != "https://api.gdeltproject.org":
            raise ValueError("GDELT_CONFIG_INVALID")
        if self.earliest_supported_at is not None and (
            self.earliest_supported_at.tzinfo is None
            or self.earliest_supported_at.utcoffset() is None
        ):
            raise ValueError("GDELT_HISTORY_TIME_NAIVE")


class GdeltProvider:
    def __init__(self, config: GdeltConfig, fetcher: ResearchDocumentFetcher) -> None:
        self.config = config
        self.fetcher = fetcher

    @staticmethod
    def build_url(config: GdeltConfig, request: DiscoveryRequestV2) -> str:
        params = {
            "query": request.query,
            "mode": "ArtList",
            "format": "json",
            "startdatetime": request.time_window.start.astimezone(UTC).strftime("%Y%m%d%H%M%S"),
            "enddatetime": request.time_window.end.astimezone(UTC).strftime("%Y%m%d%H%M%S"),
            "maxrecords": min(request.limit, 250),
            "sort": "HybridRel",
        }
        return f"{config.api_origin}/api/v2/doc/doc?{urlencode(params, quote_via=quote)}"

    async def discover(self, request: DiscoveryRequestV2) -> DiscoveryBatchV2:
        validate_source_request(request.source_id, self.config.source_id)
        started_at = now_utc()
        content = None
        dispatched = False
        try:
            if request.cursor is not None:
                raise AdapterDataError("SOURCE_HISTORY_UNSUPPORTED")
            if self.config.earliest_supported_at is not None and request.time_window.start < self.config.earliest_supported_at:
                raise AdapterDataError("SOURCE_HISTORY_UNSUPPORTED")
            url = self.build_url(self.config, request)
            dispatched = True
            content = await self.fetcher.fetch(
                FetchRequestV2(
                    request_id=_child_id(request.request_id), source_id=request.source_id,
                    tenant_id=request.tenant_id, run_id=request.run_id, lease_id=request.lease_id,
                    authorization_scope_digest=request.authorization_scope_digest,
                    candidate_id=candidate_id(request.source_id, "gdelt-query"), url=url,
                )
            )
            payload = as_mapping(parse_json(content))
            articles = payload.get("articles")
            if not isinstance(articles, list):
                raise AdapterDataError("SOURCE_SCHEMA_INVALID")
            if len(articles) > min(request.limit, 250):
                raise AdapterDataError("SOURCE_SCHEMA_INVALID")
            candidates: list[CandidateRecordV2] = []
            filtered = 0
            seen_items: set[str] = set()
            for raw in articles:
                candidate = _article_candidate(request, as_mapping(raw))
                if candidate is None or candidate.source_item_id in seen_items:
                    filtered += 1
                else:
                    candidates.append(candidate)
                    seen_items.add(candidate.source_item_id)
            truncated = len(articles) >= min(request.limit, 250)
            status: AttemptStatus = (
                "truncated" if truncated else "success" if candidates else "success_empty"
            )
            attempt = make_attempt(
                request_id=request.request_id, source_id=request.source_id, lease_id=request.lease_id,
                status=status, started_at=started_at, returned_count=len(candidates), filtered_count=filtered,
                error_code=None, requests=content.request_count, downloaded_bytes=content.downloaded_bytes,
                coverage="partial" if truncated else "unknown", cursor=None, http_status=content.status_code,
                retry_after_seconds=nonnegative_header_int(content, "retry-after"),
            )
            return DiscoveryBatchV2(
                request_id=request.request_id, candidates=tuple(candidates), next_cursor=None,
                completeness="truncated" if truncated else "unknown",
                coverage="partial" if truncated else "unknown", attempts=(attempt,),
            )
        except Exception as exc:  # noqa: BLE001
            return _failed(request, started_at, exc, content, dispatched)


def _article_candidate(request: DiscoveryRequestV2, item: Mapping[str, object]) -> CandidateRecordV2 | None:
    url = as_nonblank(item.get("url"))
    title = as_nonblank(item.get("title"))
    seen = as_nonblank(item.get("seendate"))
    if not url or not title or not seen:
        raise AdapterDataError("SOURCE_SCHEMA_INVALID")
    split = urlsplit(url)
    if split.scheme != "https" or not split.hostname or split.username is not None or split.password is not None:
        return None
    try:
        seen_at = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise AdapterDataError("SOURCE_SCHEMA_INVALID") from exc
    if not request.time_window.start <= seen_at < request.time_window.end:
        return None
    item_id = hashlib.sha256(url.encode()).hexdigest()
    labels = ["requires_content_fetch"]
    for key, prefix in (("language", "language"), ("sourcecountry", "country")):
        value = as_nonblank(item.get(key))
        if value:
            labels.append(f"{prefix}:{value}"[:128])
    return CandidateRecordV2(
        candidate_id=candidate_id(request.source_id, item_id), source_id=request.source_id,
        source_item_id=item_id, url=url, title=title,
        raw_first_seen_at=seen_at.isoformat().replace("+00:00", "Z"),
        timestamp_semantics="unknown", discovered_via="api", content_scope="none",
        labels=tuple(labels),
    )


def _failed(request, started_at, exc, content, dispatched) -> DiscoveryBatchV2:
    attempt = make_attempt(
        request_id=request.request_id, source_id=request.source_id, lease_id=request.lease_id,
        status="failed", started_at=started_at, returned_count=0, filtered_count=0,
        error_code=exception_error_code(exc),
        requests=content.request_count if content is not None else error_request_count(exc) if dispatched else 0,
        downloaded_bytes=content.downloaded_bytes if content is not None else error_downloaded_bytes(exc),
        coverage="unknown", cursor=request.cursor,
        http_status=content.status_code if content is not None else error_http_status(exc),
        retry_after_seconds=nonnegative_header_int(content, "retry-after") if content is not None else nonnegative_error_header_int(exc, "retry-after"),
    )
    return DiscoveryBatchV2(request_id=request.request_id, candidates=(), next_cursor=None, completeness="unknown", coverage="unknown", attempts=(attempt,))


def _child_id(request_id: str) -> str:
    value = f"{request_id}:gdelt"
    return value if len(value) <= 128 else "request-" + hashlib.sha256(value.encode()).hexdigest()[:32]


__all__ = ["GdeltConfig", "GdeltProvider"]
