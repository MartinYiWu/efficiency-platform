"""研究候选与已抽取正文的确定性规范化。"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from efficiency_platform_agent.contracts.research_evidence_v2 import SourceDocumentV2
from efficiency_platform_agent.contracts.research_sources_v2 import (
    CandidateRecordV2,
    ExtractedDocumentV2,
)

_TRACKING_KEYS = frozenset(
    {"fbclid", "gclid", "mc_cid", "mc_eid", "ref_src", "spm"}
)
_TIMEZONE_SUFFIX = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$", re.IGNORECASE)
_DATE_ONLY = re.compile(r"\d{4}-\d{2}-\d{2}$")


def canonicalize_url(value: str) -> str:
    """仅删除明确跟踪字段与 fragment，不改变文章身份字段。"""

    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError("CANONICAL_URL_INVALID") from exc
    if (
        parsed.scheme.lower() != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or (port is not None and port != 443)
    ):
        raise ValueError("CANONICAL_URL_INVALID")
    kept: list[str] = []
    for part in parsed.query.split("&") if parsed.query else ():
        raw_key = part.split("=", 1)[0]
        key = unquote_plus(raw_key).lower()
        if key.startswith("utm_") or key in _TRACKING_KEYS:
            continue
        kept.append(part)
    path = parsed.path or "/"
    query = "&".join(kept)
    normalized_host = host.lower()
    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    return urlunsplit(("https", normalized_host, path, query, ""))


def normalize(
    candidate: CandidateRecordV2,
    content: ExtractedDocumentV2,
) -> SourceDocumentV2:
    if not isinstance(candidate, CandidateRecordV2) or not isinstance(
        content, ExtractedDocumentV2
    ):
        raise TypeError("candidate/content 类型无效")
    if candidate.candidate_id != content.candidate_id:
        raise ValueError("NORMALIZATION_CANDIDATE_MISMATCH")
    canonical_url = canonicalize_url(content.canonical_url)
    published_at, precision, timezone_known = _publication_time(
        candidate.raw_published_at,
        content.published_at,
    )
    first_published_at = _exact_time(candidate.raw_created_at)
    updated_at = _exact_time(candidate.raw_updated_at)
    digest = hashlib.sha256(
        (
            f"{candidate.source_id}\x00{candidate.source_item_id}\x00"
            f"{content.content_hash}"
        ).encode()
    ).hexdigest()[:32]
    publisher = urlsplit(canonical_url).hostname
    if publisher is None:
        raise ValueError("CANONICAL_URL_INVALID")
    return SourceDocumentV2(
        document_id=f"document-{digest}",
        candidate_id=candidate.candidate_id,
        source_id=candidate.source_id,
        source_item_id=candidate.source_item_id,
        source_item_version=candidate.source_item_version,
        original_url=candidate.url,
        canonical_url=canonical_url,
        publisher_id=publisher,
        ownership_group=None,
        title=content.title,
        text=content.text,
        content_hash=content.content_hash,
        artifact_ref=f"inline:sha256:{content.content_hash}",
        discovered_via=candidate.discovered_via,
        content_scope=(
            candidate.content_scope if candidate.content_scope != "none" else "full"
        ),
        raw_published_at=candidate.raw_published_at,
        raw_created_at=candidate.raw_created_at,
        raw_updated_at=candidate.raw_updated_at,
        raw_first_seen_at=candidate.raw_first_seen_at,
        published_at=published_at,
        published_interval_end=None,
        published_timezone_known=timezone_known,
        time_precision=precision,
        updated_at=updated_at,
        event_at=None,
        first_published_at=first_published_at,
        first_seen_at=_exact_time(candidate.raw_first_seen_at),
        fetched_at=None,
        extractor_version=content.extractor_version,
        resource_status="accepted",
        language=None,
        event_region=None,
        source_role="unknown",
    )


def _publication_time(
    raw: str | None,
    extracted: datetime | None,
) -> tuple[
    datetime | None,
    Literal["exact", "day", "month", "unknown"],
    bool,
]:
    exact = _exact_time(raw)
    if exact is not None:
        return exact, "exact", True
    if raw is not None and _DATE_ONLY.fullmatch(raw.strip()):
        return None, "day", False
    if extracted is not None:
        if extracted.tzinfo is None or extracted.utcoffset() is None:
            return None, "unknown", False
        return extracted.astimezone(UTC), "exact", True
    return None, "unknown", False


def _exact_time(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value or not _TIMEZONE_SUFFIX.search(value):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


__all__ = ["canonicalize_url", "normalize"]
