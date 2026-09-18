"""只解析内存字节的 RSS/Atom 安全入口。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from efficiency_platform_agent.contracts.research_sources_v2 import (
    CandidateRecordV2,
    DiscoveryBatchV2,
    DiscoveryRequestV2,
    FetchRequestV2,
)

from ._adapter_support import (
    AttemptStatus,
    CompletenessStatus,
    CoverageStatus,
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
    validate_fetched,
    validate_source_request,
)
from ._process_isolation import (
    IsolatedParseFailed,
    IsolatedParseTimeout,
    run_isolated_parser,
)
from ._xml_safety import UnsafeXmlError, parse_safe_xml
from .extraction import DocumentExtractionError


@dataclass(frozen=True, slots=True)
class ParsedFeed:
    title: str
    entry_count: int
    raw_entries: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True, slots=True)
class FeedSourceConfig:
    source_id: str
    feed_url: str
    history_mode: Literal["queryable", "archive", "latest_only", "unknown"]
    access_mode: Literal["rss", "atom"] = "rss"
    # 组合根只可按已核验的正文语义与许可设置；摘要字段永不升级。
    body_content_scope: Literal["summary", "full", "platform_text"] = "summary"

    def __post_init__(self) -> None:
        split = urlsplit(self.feed_url)
        if (
            not self.source_id.strip()
            or split.scheme != "https"
            or not split.hostname
            or split.username is not None
            or split.password is not None
        ):
            raise ValueError("FEED_SOURCE_CONFIG_INVALID")
        if self.history_mode not in {"queryable", "archive", "latest_only", "unknown"}:
            raise ValueError("FEED_HISTORY_MODE_INVALID")
        if self.access_mode not in {"rss", "atom"}:
            raise ValueError("FEED_ACCESS_MODE_INVALID")
        if self.body_content_scope not in {"summary", "full", "platform_text"}:
            raise ValueError("FEED_CONTENT_SCOPE_INVALID")


class FeedSourceProvider:
    def __init__(
        self,
        config: FeedSourceConfig,
        fetcher: ResearchDocumentFetcher,
        *,
        parser: SafeFeedParser | None = None,
    ) -> None:
        self.config = config
        self.fetcher = fetcher
        self.parser = parser or SafeFeedParser()

    async def discover(self, request: DiscoveryRequestV2) -> DiscoveryBatchV2:
        validate_source_request(request.source_id, self.config.source_id)
        started_at = now_utc()
        content = None
        request_started = False
        try:
            offset = _parse_offset(request.cursor)
            fetch_request = FetchRequestV2(
                request_id=_child_request_id(request.request_id, "feed"),
                source_id=request.source_id,
                tenant_id=request.tenant_id,
                run_id=request.run_id,
                lease_id=request.lease_id,
                authorization_scope_digest=request.authorization_scope_digest,
                candidate_id=_child_request_id(request.request_id, "document"),
                url=self.config.feed_url,
            )
            request_started = True
            content = await self.fetcher.fetch(fetch_request)
            validate_fetched(
                content,
                frozenset(
                    {
                        "application/atom+xml",
                        "application/rss+xml",
                        "application/xml",
                        "text/xml",
                    }
                ),
            )
            parsed = self.parser.parse(content.body)
            candidates, filtered = _feed_candidates(
                request.source_id,
                parsed.raw_entries,
                "cache"
                if content.cache_status == "revalidated"
                else self.config.access_mode,
                self.config.body_content_scope,
            )
            page = candidates[offset : offset + request.limit]
            next_offset = offset + len(page)
            truncated = next_offset < len(candidates)
            next_cursor = str(next_offset) if truncated else None
            completeness: CompletenessStatus = "truncated" if truncated else "complete"
            coverage = _feed_coverage(self.config.history_mode, truncated)
            status: AttemptStatus = (
                "truncated" if truncated else "success" if page else "success_empty"
            )
            attempt = make_attempt(
                request_id=request.request_id,
                source_id=request.source_id,
                lease_id=request.lease_id,
                status=status,
                started_at=started_at,
                returned_count=len(page),
                filtered_count=filtered,
                error_code=None,
                requests=content.request_count,
                downloaded_bytes=content.downloaded_bytes,
                coverage=coverage,
                cursor=request.cursor,
                http_status=content.status_code,
            )
            return DiscoveryBatchV2(
                request_id=request.request_id,
                candidates=page,
                next_cursor=next_cursor,
                completeness=completeness,
                coverage=coverage,
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
                    content.request_count
                    if content is not None
                    else error_request_count(exc)
                    if request_started
                    else 0
                ),
                downloaded_bytes=(
                    content.downloaded_bytes
                    if content is not None
                    else error_downloaded_bytes(exc)
                ),
                coverage="unknown",
                cursor=request.cursor,
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
            )
            return DiscoveryBatchV2(
                request_id=request.request_id,
                candidates=(),
                next_cursor=None,
                completeness="unknown",
                coverage="unknown",
                attempts=(attempt,),
            )


class SafeFeedParser:
    def __init__(
        self,
        *,
        parser: Callable[[bytes], Mapping[str, Any]] | None = None,
        allow_in_process_test_parser: bool = False,
        parse_timeout_seconds: float = 3.0,
        max_body_bytes: int = 2 * 1024 * 1024,
        max_depth: int = 32,
        max_nodes: int = 20_000,
    ) -> None:
        if parser is not None and not allow_in_process_test_parser:
            raise ValueError("IN_PROCESS_TEST_PARSER_NOT_ALLOWED")
        if parse_timeout_seconds <= 0:
            raise ValueError("PARSE_TIMEOUT_INVALID")
        self.parser = parser
        self.parse_timeout_seconds = parse_timeout_seconds
        self.max_body_bytes = max_body_bytes
        self.max_depth = max_depth
        self.max_nodes = max_nodes

    def parse(self, body: bytes) -> ParsedFeed:
        if not isinstance(body, bytes) or not body or len(body) > self.max_body_bytes:
            raise DocumentExtractionError("CONTENT_REJECTED", "FEED_SIZE_INVALID")
        try:
            parse_safe_xml(body, max_depth=self.max_depth, max_nodes=self.max_nodes)
        except UnsafeXmlError as exc:
            code = (
                "SOURCE_SCHEMA_INVALID"
                if str(exc) == "XML_INVALID"
                else "CONTENT_REJECTED"
            )
            raise DocumentExtractionError(code, str(exc)) from exc
        try:
            if self.parser is None:
                result = run_isolated_parser(
                    "feed", body, timeout_seconds=self.parse_timeout_seconds
                )
                if not isinstance(result, Mapping):
                    raise DocumentExtractionError(
                        "SOURCE_SCHEMA_INVALID", "FEED_SHAPE_INVALID"
                    )
                parsed = result
            else:
                parsed = self.parser(body)
        except IsolatedParseTimeout as exc:
            raise DocumentExtractionError(
                "CONTENT_UNAVAILABLE", "FEED_PARSE_TIMEOUT"
            ) from exc
        except IsolatedParseFailed as exc:
            raise DocumentExtractionError(
                "SOURCE_SCHEMA_INVALID", "FEED_PARSER_FAILED"
            ) from exc
        except Exception as exc:
            if isinstance(exc, DocumentExtractionError):
                raise
            raise DocumentExtractionError(
                "SOURCE_SCHEMA_INVALID", "FEED_PARSER_FAILED"
            ) from exc
        if bool(parsed.get("bozo", False)):
            raise DocumentExtractionError("SOURCE_SCHEMA_INVALID", "FEED_MALFORMED")
        feed = parsed.get("feed", {})
        entries = parsed.get("entries", ())
        if not isinstance(feed, Mapping) or not isinstance(entries, (list, tuple)):
            raise DocumentExtractionError("SOURCE_SCHEMA_INVALID", "FEED_SHAPE_INVALID")
        title = str(feed.get("title") or "Untitled feed").strip()
        normalized_entries: list[Mapping[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise DocumentExtractionError(
                    "SOURCE_SCHEMA_INVALID", "FEED_ENTRY_INVALID"
                )
            normalized_entries.append(entry)
        return ParsedFeed(title, len(normalized_entries), tuple(normalized_entries))


def _feed_candidates(
    source_id: str,
    entries: tuple[Mapping[str, Any], ...],
    access_mode: Literal["rss", "atom", "cache"],
    body_content_scope: Literal["summary", "full", "platform_text"] = "summary",
) -> tuple[tuple[CandidateRecordV2, ...], int]:
    candidates: list[CandidateRecordV2] = []
    known_ids: set[str] = set()
    filtered = 0
    for raw_entry in entries:
        entry = as_mapping(raw_entry)
        link = as_nonblank(entry.get("link"))
        title = as_nonblank(entry.get("title"))
        item_id = as_nonblank(entry.get("id")) or as_nonblank(entry.get("guid")) or link
        if not link or not title or not item_id or not _is_https_url(link):
            filtered += 1
            continue
        if item_id in known_ids:
            filtered += 1
            continue
        known_ids.add(item_id)
        inline_content, scope = _feed_content(entry, body_content_scope)
        published = as_nonblank(entry.get("published"))
        updated = as_nonblank(entry.get("updated"))
        try:
            candidates.append(
                CandidateRecordV2(
                    candidate_id=candidate_id(source_id, item_id),
                    source_id=source_id,
                    source_item_id=item_id,
                    url=link,
                    title=title,
                    raw_published_at=published,
                    raw_updated_at=updated,
                    timestamp_semantics=(
                        "published"
                        if published
                        else "updated"
                        if updated
                        else "unknown"
                    ),
                    discovered_via=access_mode,
                    content_scope=scope,
                    inline_content=inline_content,
                    labels=("attributed_platform_text_only",)
                    if scope == "platform_text"
                    else (),
                )
            )
        except ValueError:
            filtered += 1
    return tuple(candidates), filtered


def _feed_content(
    entry: Mapping[str, Any],
    body_content_scope: Literal["summary", "full", "platform_text"],
) -> tuple[str | None, Literal["none", "summary", "full", "platform_text"]]:
    content = entry.get("content")
    if isinstance(content, (list, tuple)):
        for item in content:
            if isinstance(item, Mapping):
                cleaned = clean_fragment(item.get("value"))
                if cleaned:
                    return cleaned, body_content_scope
    summary = clean_fragment(entry.get("summary")) or clean_fragment(
        entry.get("description")
    )
    return (summary, "summary") if summary else (None, "none")


def _parse_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isascii() or not cursor.isdigit():
        raise ValueError("FEED_CURSOR_INVALID")
    offset = int(cursor)
    if offset < 0 or offset > 1_000_000:
        raise ValueError("FEED_CURSOR_INVALID")
    return offset


def _feed_coverage(
    history_mode: Literal["queryable", "archive", "latest_only", "unknown"],
    truncated: bool,
) -> CoverageStatus:
    if history_mode not in {"queryable", "archive"}:
        return "unknown"
    return "partial" if truncated else "complete"


def _is_https_url(value: str) -> bool:
    split = urlsplit(value)
    return split.scheme == "https" and bool(split.hostname)


def _child_request_id(request_id: str, purpose: str) -> str:
    value = f"{request_id}:{purpose}"
    return value if len(value) <= 128 else candidate_id("request", value)


__all__ = [
    "FeedSourceConfig",
    "FeedSourceProvider",
    "ParsedFeed",
    "SafeFeedParser",
]
