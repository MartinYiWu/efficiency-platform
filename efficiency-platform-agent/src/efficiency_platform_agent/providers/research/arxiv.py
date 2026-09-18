"""arXiv Atom API 的只读元数据/摘要适配器。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
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
    candidate_id,
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
from ._xml_safety import UnsafeXmlError, parse_safe_xml

_CATEGORY = re.compile(r"[A-Za-z0-9.-]{1,64}")
_ATOM = "{http://www.w3.org/2005/Atom}"
_OPEN_SEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"


@dataclass(frozen=True, slots=True)
class ArxivConfig:
    source_id: str
    categories: tuple[str, ...] = ()
    api_origin: str = "https://export.arxiv.org"

    def __post_init__(self) -> None:
        if (
            not self.source_id.strip()
            or self.api_origin != "https://export.arxiv.org"
            or len(set(self.categories)) != len(self.categories)
            or any(not _CATEGORY.fullmatch(item) for item in self.categories)
        ):
            raise ValueError("ARXIV_CONFIG_INVALID")


class ArxivProvider:
    def __init__(self, config: ArxivConfig, fetcher: ResearchDocumentFetcher) -> None:
        self.config = config
        self.fetcher = fetcher

    @staticmethod
    def build_url(config: ArxivConfig, request: DiscoveryRequestV2) -> str:
        start = _parse_offset(request.cursor)
        start_text = request.time_window.start.strftime("%Y%m%d%H%M")
        end_text = request.time_window.end.strftime("%Y%m%d%H%M")
        parts = [f'all:"{request.query}"', f"submittedDate:[{start_text} TO {end_text}]"]
        if config.categories:
            parts.append("(" + " OR ".join(f"cat:{item}" for item in config.categories) + ")")
        params = {
            "search_query": " AND ".join(parts),
            "start": start,
            "max_results": min(request.limit, 100),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        return f"{config.api_origin}/api/query?{urlencode(params, quote_via=quote)}"

    async def discover(self, request: DiscoveryRequestV2) -> DiscoveryBatchV2:
        validate_source_request(request.source_id, self.config.source_id)
        started_at = now_utc()
        content = None
        dispatched = False
        try:
            offset = _parse_offset(request.cursor)
            url = self.build_url(self.config, request)
            dispatched = True
            content = await self.fetcher.fetch(
                FetchRequestV2(
                    request_id=_child_id(request.request_id),
                    source_id=request.source_id,
                    tenant_id=request.tenant_id,
                    run_id=request.run_id,
                    lease_id=request.lease_id,
                    authorization_scope_digest=request.authorization_scope_digest,
                    candidate_id=candidate_id(request.source_id, f"page:{offset}"),
                    url=url,
                )
            )
            validate_fetched(
                content,
                frozenset(
                    {"application/atom+xml", "application/xml", "text/xml"}
                ),
            )
            try:
                root = parse_safe_xml(content.body)
            except UnsafeXmlError as exc:
                raise AdapterDataError("SOURCE_SCHEMA_INVALID") from exc
            total = _required_nonnegative_int(root.findtext(f"{_OPEN_SEARCH}totalResults"))
            entries = root.findall(f"{_ATOM}entry")
            if len(entries) > min(request.limit, 100):
                raise AdapterDataError("SOURCE_SCHEMA_INVALID")
            candidates: list[CandidateRecordV2] = []
            filtered = 0
            for entry in entries:
                candidate = _entry_candidate(request, entry)
                if candidate is None:
                    filtered += 1
                else:
                    candidates.append(candidate)
            if len({item.source_item_id for item in candidates}) != len(candidates):
                raise AdapterDataError("SOURCE_SCHEMA_INVALID")
            next_offset = offset + min(request.limit, 100)
            truncated = next_offset < total
            status: AttemptStatus = (
                "truncated" if truncated else "success" if candidates else "success_empty"
            )
            attempt = make_attempt(
                request_id=request.request_id,
                source_id=request.source_id,
                lease_id=request.lease_id,
                status=status,
                started_at=started_at,
                returned_count=len(candidates),
                filtered_count=filtered,
                error_code=None,
                requests=content.request_count,
                downloaded_bytes=content.downloaded_bytes,
                coverage="partial" if truncated else "complete",
                cursor=request.cursor,
                http_status=content.status_code,
                retry_after_seconds=nonnegative_header_int(content, "retry-after"),
            )
            return DiscoveryBatchV2(
                request_id=request.request_id,
                candidates=tuple(candidates),
                next_cursor=str(next_offset) if truncated else None,
                completeness="truncated" if truncated else "complete",
                coverage="partial" if truncated else "complete",
                attempts=(attempt,),
            )
        except Exception as exc:  # noqa: BLE001
            return _failed(request, started_at, exc, content, dispatched)


def _entry_candidate(request: DiscoveryRequestV2, entry) -> CandidateRecordV2 | None:
    url = _text(entry.findtext(f"{_ATOM}id"))
    title = _text(entry.findtext(f"{_ATOM}title"))
    summary = _text(entry.findtext(f"{_ATOM}summary"))
    published = _text(entry.findtext(f"{_ATOM}published"))
    updated = _text(entry.findtext(f"{_ATOM}updated"))
    if (
        url is None
        or title is None
        or summary is None
        or published is None
        or updated is None
    ):
        raise AdapterDataError("SOURCE_SCHEMA_INVALID")
    split = urlsplit(url)
    if split.scheme != "https" or split.hostname != "arxiv.org" or not split.path.startswith("/abs/"):
        raise AdapterDataError("SOURCE_SCHEMA_INVALID")
    published_at = _iso_time(published)
    _iso_time(updated)
    if not request.time_window.start <= published_at < request.time_window.end:
        return None
    item_id = split.path.removeprefix("/abs/")
    categories = tuple(
        term
        for node in entry.findall(f"{_ATOM}category")
        if (term := node.attrib.get("term")) and _CATEGORY.fullmatch(term)
    )
    return CandidateRecordV2(
        candidate_id=candidate_id(request.source_id, item_id),
        source_id=request.source_id,
        source_item_id=item_id,
        source_item_version=updated,
        url=url,
        title=title,
        raw_published_at=published,
        raw_created_at=published,
        raw_updated_at=updated,
        timestamp_semantics="published",
        discovered_via="api",
        content_scope="summary",
        inline_content=summary,
        labels=tuple(dict.fromkeys((*categories, "abstract_only"))),
    )


def _failed(request, started_at, exc, content, dispatched) -> DiscoveryBatchV2:
    attempt = make_attempt(
        request_id=request.request_id,
        source_id=request.source_id,
        lease_id=request.lease_id,
        status="failed",
        started_at=started_at,
        returned_count=0,
        filtered_count=0,
        error_code=exception_error_code(exc),
        requests=content.request_count if content is not None else error_request_count(exc) if dispatched else 0,
        downloaded_bytes=content.downloaded_bytes if content is not None else error_downloaded_bytes(exc),
        coverage="unknown",
        cursor=request.cursor,
        http_status=content.status_code if content is not None else error_http_status(exc),
        retry_after_seconds=nonnegative_header_int(content, "retry-after") if content is not None else nonnegative_error_header_int(exc, "retry-after"),
    )
    return DiscoveryBatchV2(request_id=request.request_id, candidates=(), next_cursor=None, completeness="unknown", coverage="unknown", attempts=(attempt,))


def _parse_offset(value: str | None) -> int:
    if value is None:
        return 0
    if not value.isascii() or not value.isdigit() or int(value) > 1_000_000:
        raise AdapterDataError("SOURCE_SCHEMA_INVALID")
    return int(value)


def _required_nonnegative_int(value: str | None) -> int:
    if value is None or not value.isascii() or not value.isdigit():
        raise AdapterDataError("SOURCE_SCHEMA_INVALID")
    return int(value)


def _iso_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AdapterDataError("SOURCE_SCHEMA_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AdapterDataError("SOURCE_SCHEMA_INVALID")
    return parsed


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _child_id(request_id: str) -> str:
    value = f"{request_id}:arxiv"
    return value if len(value) <= 128 else "request-" + hashlib.sha256(value.encode()).hexdigest()[:32]


__all__ = ["ArxivConfig", "ArxivProvider"]
