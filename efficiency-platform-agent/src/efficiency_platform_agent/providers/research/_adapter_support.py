"""研究来源适配器的共享离线契约辅助。"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any, Literal, Protocol

from efficiency_platform_agent.contracts.research_sources_v2 import (
    FetchedContentV2,
    FetchRequestV2,
    SourceAttemptV2,
    SourceUsageV2,
)


class ResearchDocumentFetcher(Protocol):
    async def fetch(self, request: FetchRequestV2) -> FetchedContentV2: ...


class AdapterDataError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


AttemptStatus = Literal[
    "success", "success_empty", "failed", "truncated", "cancelled"
]
CoverageStatus = Literal["complete", "partial", "unknown"]
CompletenessStatus = Literal["complete", "truncated", "unknown"]


def now_utc() -> datetime:
    return datetime.now(UTC)


def validate_source_request(request_source_id: str, configured_source_id: str) -> None:
    if request_source_id != configured_source_id:
        raise ValueError("SOURCE_REQUEST_MISMATCH")


def validate_fetched(content: FetchedContentV2, allowed_media: frozenset[str]) -> None:
    status_error = status_error_code(content.status_code)
    if status_error:
        raise AdapterDataError(status_error)
    if content.media_type.split(";", 1)[0].lower() not in allowed_media:
        raise AdapterDataError("SOURCE_SCHEMA_INVALID")


def parse_json(content: FetchedContentV2) -> Any:
    validate_fetched(content, frozenset({"application/json"}))
    try:
        return json.loads(content.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterDataError("SOURCE_SCHEMA_INVALID") from exc


def status_error_code(status_code: int) -> str | None:
    if 200 <= status_code < 300:
        return None
    if status_code == 304:
        return "CONTENT_UNAVAILABLE"
    if status_code == 401:
        return "SOURCE_AUTH_REQUIRED"
    if status_code == 403:
        return "SOURCE_FORBIDDEN"
    if status_code == 429:
        return "SOURCE_RATE_LIMITED"
    if status_code == 408 or 500 <= status_code < 600:
        return "SOURCE_TEMPORARY_FAILURE"
    return "CONTENT_UNAVAILABLE"


def exception_error_code(error: Exception) -> str:
    if isinstance(error, AdapterDataError):
        return error.code
    reason_code = getattr(error, "reason_code", None)
    if reason_code in {
        "SOURCE_AUTH_REQUIRED",
        "SOURCE_FORBIDDEN",
        "SOURCE_RATE_LIMITED",
        "SOURCE_TEMPORARY_FAILURE",
    }:
        return str(reason_code)
    code = getattr(error, "code", None)
    if code in {
        "CONTENT_REJECTED",
        "CONTENT_UNAVAILABLE",
        "SOURCE_SCHEMA_INVALID",
        "SOURCE_AUTH_REQUIRED",
        "SOURCE_FORBIDDEN",
        "SOURCE_RATE_LIMITED",
        "SOURCE_TEMPORARY_FAILURE",
    }:
        return str(code)
    return "CONTENT_UNAVAILABLE"


def candidate_id(source_id: str, item_id: str) -> str:
    digest = hashlib.sha256(f"{source_id}\n{item_id}".encode()).hexdigest()
    return f"candidate-{digest[:32]}"


def make_attempt(
    *,
    request_id: str,
    source_id: str,
    lease_id: str,
    status: AttemptStatus,
    started_at: datetime,
    returned_count: int,
    filtered_count: int,
    error_code: str | None,
    requests: int,
    downloaded_bytes: int,
    coverage: CoverageStatus,
    cursor: str | None,
    http_status: int | None,
    rate_limit_remaining: int | None = None,
    retry_after_seconds: int | None = None,
) -> SourceAttemptV2:
    attempt_digest = hashlib.sha256(
        f"{source_id}:{request_id}".encode()
    ).hexdigest()[:32]
    return SourceAttemptV2(
        attempt_id=f"attempt-{attempt_digest}",
        action_id=request_id,
        source_id=source_id,
        status=status,
        started_at=started_at,
        finished_at=now_utc(),
        returned_count=returned_count,
        filtered_count=filtered_count,
        error_code=error_code,
        coverage=coverage,
        cursor=cursor,
        http_status=http_status,
        rate_limit_remaining=rate_limit_remaining,
        retry_after_seconds=retry_after_seconds,
        lease_id=lease_id,
        usage=SourceUsageV2(
            requests=requests,
            returned_items=returned_count,
            downloaded_bytes=downloaded_bytes,
        ),
    )


def response_header(content: FetchedContentV2, name: str) -> str | None:
    target = name.lower()
    return next((value for key, value in content.response_headers if key == target), None)


def nonnegative_header_int(content: FetchedContentV2, name: str) -> int | None:
    target = name.lower()
    value = response_header(content, name)
    if value is None or not value.isascii() or not value.isdigit():
        return None
    parsed = int(value)
    if parsed < 0:
        return None
    return min(parsed, 86_400) if target == "retry-after" else parsed


def nonnegative_error_header_int(exc: Exception, name: str) -> int | None:
    target = name.lower()
    headers = getattr(exc, "response_headers", ())
    if not isinstance(headers, tuple):
        return None
    value = next(
        (
            header_value
            for header_name, header_value in headers
            if header_name == target
        ),
        None,
    )
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        return None
    parsed = int(value)
    if parsed < 0:
        return None
    return min(parsed, 86_400) if target == "retry-after" else parsed


def error_http_status(exc: Exception) -> int | None:
    value = getattr(exc, "http_status", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def error_downloaded_bytes(exc: Exception) -> int:
    value = getattr(exc, "downloaded_bytes", 0)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def error_request_count(exc: Exception) -> int:
    value = getattr(exc, "request_count", 0)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def clean_fragment(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parser = _TextParser()
    parser.feed(value)
    text = unescape(" ".join(parser.parts))
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized or None


def as_nonblank(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def as_mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AdapterDataError("SOURCE_SCHEMA_INVALID")
    return value


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style", "noscript"}:
            self.blocked_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self.blocked_depth:
            self.blocked_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.blocked_depth and data.strip():
            self.parts.append(data.strip())


__all__ = [
    "AdapterDataError",
    "AttemptStatus",
    "CompletenessStatus",
    "CoverageStatus",
    "ResearchDocumentFetcher",
    "as_mapping",
    "as_nonblank",
    "candidate_id",
    "clean_fragment",
    "exception_error_code",
    "make_attempt",
    "nonnegative_header_int",
    "now_utc",
    "parse_json",
    "response_header",
    "validate_fetched",
    "validate_source_request",
]
