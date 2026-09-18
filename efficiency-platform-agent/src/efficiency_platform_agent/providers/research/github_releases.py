"""固定仓库白名单的 GitHub Releases 离线适配器。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlencode

from efficiency_platform_agent.contracts.research_sources_v2 import (
    CandidateRecordV2,
    DiscoveryBatchV2,
    DiscoveryRequestV2,
    FetchRequestV2,
)

from ._adapter_support import (
    AdapterDataError,
    AttemptStatus,
    CompletenessStatus,
    CoverageStatus,
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
    response_header,
    validate_source_request,
)

_REPO_PART = re.compile(r"[A-Za-z0-9_.-]{1,100}")


@dataclass(frozen=True, slots=True)
class GitHubReleasesConfig:
    source_id: str
    owner: str
    repository: str
    api_origin: str = "https://api.github.com"

    def __post_init__(self) -> None:
        if (
            not self.source_id.strip()
            or not _REPO_PART.fullmatch(self.owner)
            or not _REPO_PART.fullmatch(self.repository)
            or self.owner in {".", ".."}
            or self.repository in {".", ".."}
            or self.api_origin != "https://api.github.com"
        ):
            raise ValueError("GITHUB_RELEASES_CONFIG_INVALID")

    @property
    def endpoint(self) -> str:
        return f"{self.api_origin}/repos/{self.owner}/{self.repository}/releases"


class GitHubReleasesProvider:
    def __init__(
        self,
        config: GitHubReleasesConfig,
        fetcher: ResearchDocumentFetcher,
    ) -> None:
        self.config = config
        self.fetcher = fetcher

    async def discover(self, request: DiscoveryRequestV2) -> DiscoveryBatchV2:
        validate_source_request(request.source_id, self.config.source_id)
        started_at = now_utc()
        content = None
        request_started = False
        try:
            page = _parse_page(request.cursor)
            per_page = min(request.limit, 100)
            url = f"{self.config.endpoint}?{urlencode({'page': page, 'per_page': per_page})}"
            request_started = True
            content = await self.fetcher.fetch(
                FetchRequestV2(
                    request_id=_child_request_id(request.request_id),
                    source_id=request.source_id,
                    tenant_id=request.tenant_id,
                    run_id=request.run_id,
                    lease_id=request.lease_id,
                    authorization_scope_digest=request.authorization_scope_digest,
                    candidate_id=candidate_id(request.source_id, f"page:{page}"),
                    url=url,
                )
            )
            payload = parse_json(content)
            if not isinstance(payload, list):
                raise AdapterDataError("SOURCE_SCHEMA_INVALID")
            candidates: list[CandidateRecordV2] = []
            filtered = 0
            for raw_item in payload:
                item = as_mapping(raw_item)
                if not isinstance(item.get("draft"), bool) or not isinstance(
                    item.get("prerelease"), bool
                ):
                    raise AdapterDataError("SOURCE_SCHEMA_INVALID")
                if item.get("draft") is True:
                    filtered += 1
                    continue
                try:
                    candidate = _release_candidate(request.source_id, item)
                except ValueError:
                    candidate = None
                if candidate is None:
                    filtered += 1
                    continue
                candidates.append(candidate)
                if len(candidates) >= request.limit:
                    break
            has_next = _has_next_page(response_header(content, "link"))
            truncated = has_next or len(candidates) < len(
                [
                    item
                    for item in payload
                    if isinstance(item, Mapping) and item.get("draft") is not True
                ]
            )
            next_cursor = str(page + 1) if has_next else None
            completeness: CompletenessStatus = "truncated" if truncated else "complete"
            coverage: CoverageStatus = "partial" if truncated else "complete"
            status: AttemptStatus = (
                "truncated"
                if truncated
                else "success"
                if candidates
                else "success_empty"
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
                coverage=coverage,
                cursor=request.cursor,
                http_status=content.status_code,
                rate_limit_remaining=nonnegative_header_int(
                    content, "x-ratelimit-remaining"
                ),
                retry_after_seconds=nonnegative_header_int(content, "retry-after"),
            )
            return DiscoveryBatchV2(
                request_id=request.request_id,
                candidates=tuple(candidates),
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
                rate_limit_remaining=(
                    nonnegative_header_int(content, "x-ratelimit-remaining")
                    if content is not None
                    else nonnegative_error_header_int(exc, "x-ratelimit-remaining")
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


def _release_candidate(
    source_id: str, item: Mapping[str, object]
) -> CandidateRecordV2 | None:
    raw_id = item.get("id")
    item_id = (
        str(raw_id)
        if isinstance(raw_id, (int, str)) and not isinstance(raw_id, bool)
        else None
    )
    url = as_nonblank(item.get("html_url"))
    tag = as_nonblank(item.get("tag_name"))
    title = as_nonblank(item.get("name")) or tag
    if not item_id or not url or not title or not url.startswith("https://github.com/"):
        return None
    body = as_nonblank(item.get("body"))
    published = as_nonblank(item.get("published_at"))
    created = as_nonblank(item.get("created_at"))
    prerelease = item.get("prerelease") is True
    return CandidateRecordV2(
        candidate_id=candidate_id(source_id, item_id),
        source_id=source_id,
        source_item_id=item_id,
        source_item_version=tag,
        url=url,
        title=title,
        raw_published_at=published,
        raw_created_at=created,
        timestamp_semantics="published" if published else "unknown",
        discovered_via="api",
        content_scope="platform_text" if body else "none",
        inline_content=body,
        labels=(("prerelease",) if prerelease else ())
        + (("attributed_release_notes_only",) if body else ()),
    )


def _parse_page(cursor: str | None) -> int:
    if cursor is None:
        return 1
    if not cursor.isascii() or not cursor.isdigit():
        raise AdapterDataError("SOURCE_SCHEMA_INVALID")
    page = int(cursor)
    if page < 1 or page > 10_000:
        raise AdapterDataError("SOURCE_SCHEMA_INVALID")
    return page


def _has_next_page(link_header: str | None) -> bool:
    return bool(link_header and re.search(r";\s*rel=\"next\"", link_header))


def _child_request_id(request_id: str) -> str:
    value = f"{request_id}:github-releases"
    return value if len(value) <= 128 else candidate_id("request", value)


__all__ = ["GitHubReleasesConfig", "GitHubReleasesProvider"]
