"""Hacker News 列表与 item 两层只读适配器。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

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
    clean_fragment,
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

_HN_ORIGIN = "https://hacker-news.firebaseio.com"


@dataclass(frozen=True, slots=True)
class HackerNewsConfig:
    source_id: str
    list_name: str = "topstories"
    max_concurrency: int = 4
    max_items: int = 50

    def __post_init__(self) -> None:
        if (
            not self.source_id.strip()
            or self.list_name not in {"topstories", "newstories", "beststories"}
            or not 1 <= self.max_concurrency <= 10
            or not 1 <= self.max_items <= 100
        ):
            raise ValueError("HACKER_NEWS_CONFIG_INVALID")

    @property
    def list_url(self) -> str:
        return f"{_HN_ORIGIN}/v0/{self.list_name}.json"

    def item_url(self, item_id: int) -> str:
        return f"{_HN_ORIGIN}/v0/item/{item_id}.json"


@dataclass(frozen=True, slots=True)
class _ItemResult:
    candidate: CandidateRecordV2 | None
    error_code: str | None
    downloaded_bytes: int
    http_status: int | None
    filtered: int = 0
    retry_after_seconds: int | None = None
    request_count: int = 1


class HackerNewsProvider:
    def __init__(
        self,
        config: HackerNewsConfig,
        fetcher: ResearchDocumentFetcher,
    ) -> None:
        self.config = config
        self.fetcher = fetcher

    async def discover(self, request: DiscoveryRequestV2) -> DiscoveryBatchV2:
        validate_source_request(request.source_id, self.config.source_id)
        started_at = now_utc()
        list_content = None
        list_request_started = False
        try:
            offset = _parse_offset(request.cursor)
            list_request_started = True
            list_content = await self.fetcher.fetch(
                FetchRequestV2(
                    request_id=_child_request_id(request.request_id, "list"),
                    source_id=request.source_id,
                    tenant_id=request.tenant_id,
                    run_id=request.run_id,
                    lease_id=request.lease_id,
                    authorization_scope_digest=request.authorization_scope_digest,
                    candidate_id=candidate_id(request.source_id, self.config.list_name),
                    url=self.config.list_url,
                )
            )
            payload = parse_json(list_content)
            if not isinstance(payload, list) or any(
                not isinstance(item, int) or isinstance(item, bool) or item <= 0
                for item in payload
            ):
                raise AdapterDataError("SOURCE_SCHEMA_INVALID")
            item_ids = tuple(dict.fromkeys(payload))
            selected = item_ids[
                offset : offset + min(request.limit, self.config.max_items)
            ]
            semaphore = asyncio.Semaphore(self.config.max_concurrency)
            results = await asyncio.gather(
                *(
                    self._fetch_item(request, item_id, semaphore)
                    for item_id in selected
                )
            )
            candidates = tuple(
                result.candidate
                for result in results
                if result.candidate is not None
            )
            errors = tuple(
                result.error_code for result in results if result.error_code is not None
            )
            filtered = sum(result.filtered for result in results)
            next_offset = offset + len(selected)
            has_more = next_offset < len(item_ids)
            incomplete = has_more or bool(errors)
            if errors and not candidates:
                status: AttemptStatus = "failed"
            elif incomplete:
                status = "truncated"
            elif candidates:
                status = "success"
            else:
                status = "success_empty"
            attempt = make_attempt(
                request_id=request.request_id,
                source_id=request.source_id,
                lease_id=request.lease_id,
                status=status,
                started_at=started_at,
                returned_count=len(candidates),
                filtered_count=filtered,
                error_code=errors[0] if errors else None,
                requests=list_content.request_count
                + sum(result.request_count for result in results),
                downloaded_bytes=list_content.downloaded_bytes
                + sum(result.downloaded_bytes for result in results),
                coverage="unknown",
                cursor=request.cursor,
                http_status=list_content.status_code,
                retry_after_seconds=max(
                    (
                        result.retry_after_seconds or 0
                        for result in results
                        if result.error_code is not None
                    ),
                    default=0,
                )
                or None,
            )
            return DiscoveryBatchV2(
                request_id=request.request_id,
                candidates=candidates,
                next_cursor=str(next_offset) if has_more else None,
                completeness="truncated" if incomplete else "complete",
                coverage="unknown",
                attempts=(attempt,),
            )
        except Exception as exc:  # noqa: BLE001 - Provider 边界统一安全错误
            error = exception_error_code(exc)
            attempt = make_attempt(
                request_id=request.request_id,
                source_id=request.source_id,
                lease_id=request.lease_id,
                status="failed",
                started_at=started_at,
                returned_count=0,
                filtered_count=0,
                error_code=error,
                requests=(
                    list_content.request_count
                    if list_content is not None
                    else error_request_count(exc)
                    if list_request_started
                    else 0
                ),
                downloaded_bytes=(
                    list_content.downloaded_bytes
                    if list_content is not None
                    else error_downloaded_bytes(exc)
                ),
                coverage="unknown",
                cursor=request.cursor,
                http_status=(
                    list_content.status_code
                    if list_content is not None
                    else error_http_status(exc)
                ),
                retry_after_seconds=(
                    nonnegative_header_int(list_content, "retry-after")
                    if list_content is not None
                    else nonnegative_error_header_int(exc, "retry-after")
                ),
            )
            return DiscoveryBatchV2(
                request_id=request.request_id,
                candidates=(),
                next_cursor=None,
                completeness="unknown",
                coverage="unknown",
                attempts=(attempt,),
            )

    async def _fetch_item(
        self,
        request: DiscoveryRequestV2,
        item_id: int,
        semaphore: asyncio.Semaphore,
    ) -> _ItemResult:
        content = None
        try:
            async with semaphore:
                content = await self.fetcher.fetch(
                    FetchRequestV2(
                        request_id=_child_request_id(request.request_id, str(item_id)),
                        source_id=request.source_id,
                        tenant_id=request.tenant_id,
                        run_id=request.run_id,
                        lease_id=request.lease_id,
                        authorization_scope_digest=request.authorization_scope_digest,
                        candidate_id=candidate_id(request.source_id, str(item_id)),
                        url=self.config.item_url(item_id),
                    )
                )
            payload = as_mapping(parse_json(content))
            candidate = _item_candidate(request.source_id, item_id, payload)
            return _ItemResult(
                candidate=candidate,
                error_code=None,
                downloaded_bytes=content.downloaded_bytes,
                http_status=content.status_code,
                filtered=0 if candidate is not None else 1,
                retry_after_seconds=None,
                request_count=content.request_count,
            )
        except Exception as exc:  # noqa: BLE001 - 单 item 失败必须隔离
            return _ItemResult(
                candidate=None,
                error_code=exception_error_code(exc),
                downloaded_bytes=(
                    content.downloaded_bytes
                    if content is not None
                    else error_downloaded_bytes(exc)
                ),
                http_status=(
                    content.status_code
                    if content is not None
                    else error_http_status(exc)
                ),
                retry_after_seconds=(
                    nonnegative_header_int(content, "retry-after")
                    if content is not None
                    else nonnegative_error_header_int(exc, "retry-after")
                ),
                request_count=(
                    content.request_count
                    if content is not None
                    else error_request_count(exc)
                ),
            )


def _item_candidate(
    source_id: str,
    expected_item_id: int,
    item: dict[str, object] | object,
) -> CandidateRecordV2 | None:
    mapping = as_mapping(item)
    if (
        mapping.get("id") != expected_item_id
        or mapping.get("deleted") is True
        or mapping.get("dead") is True
        or mapping.get("type") != "story"
    ):
        return None
    title = as_nonblank(mapping.get("title"))
    if not title:
        return None
    external_url = _safe_external_url(as_nonblank(mapping.get("url")))
    url = external_url or f"https://news.ycombinator.com/item?id={expected_item_id}"
    raw_time = mapping.get("time")
    posted_at = (
        datetime.fromtimestamp(raw_time, tz=UTC).isoformat()
        if isinstance(raw_time, int) and not isinstance(raw_time, bool) and raw_time >= 0
        else None
    )
    text = clean_fragment(mapping.get("text"))
    score = mapping.get("score")
    descendants = mapping.get("descendants")
    heat_parts = []
    if isinstance(score, int) and not isinstance(score, bool) and score >= 0:
        heat_parts.append(f"hn_score={score}")
    if (
        isinstance(descendants, int)
        and not isinstance(descendants, bool)
        and descendants >= 0
    ):
        heat_parts.append(f"hn_descendants={descendants}")
    return CandidateRecordV2(
        candidate_id=candidate_id(source_id, str(expected_item_id)),
        source_id=source_id,
        source_item_id=str(expected_item_id),
        url=url,
        title=title,
        raw_published_at=posted_at,
        timestamp_semantics="platform_posted" if posted_at else "unknown",
        discovered_via="api",
        heat_observation=";".join(heat_parts) or None,
        content_scope="platform_text" if text else "none",
        inline_content=text,
    )


def _parse_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isascii() or not cursor.isdigit():
        raise AdapterDataError("SOURCE_SCHEMA_INVALID")
    offset = int(cursor)
    if offset < 0 or offset > 1_000_000:
        raise AdapterDataError("SOURCE_SCHEMA_INVALID")
    return offset


def _safe_external_url(value: str | None) -> str | None:
    if value is None:
        return None
    split = urlsplit(value)
    if (
        split.scheme != "https"
        or not split.hostname
        or split.username is not None
        or split.password is not None
    ):
        return None
    return value


def _child_request_id(request_id: str, suffix: str) -> str:
    value = f"{request_id}:hn:{suffix}"
    return value if len(value) <= 128 else candidate_id("request", value)


__all__ = ["HackerNewsConfig", "HackerNewsProvider"]
