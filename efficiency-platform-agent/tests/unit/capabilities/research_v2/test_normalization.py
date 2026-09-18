"""R05 文档规范化与 URL 身份测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from efficiency_platform_agent.capabilities.research.v2.normalization import (
    canonicalize_url,
    normalize,
)
from efficiency_platform_agent.contracts.research_sources_v2 import (
    CandidateRecordV2,
    ExtractedDocumentV2,
)


def _candidate(**changes: object) -> CandidateRecordV2:
    values: dict[str, object] = {
        "candidate_id": "candidate-1",
        "source_id": "source-1",
        "source_item_id": "article-1",
        "source_item_version": "v1",
        "url": "https://News.Example/read?id=1&utm_source=test#top",
        "title": "Candidate title",
        "raw_published_at": "2026-09-15T10:00:00+08:00",
        "raw_created_at": "2026-09-15T09:00:00+08:00",
        "raw_updated_at": "2026-09-15T11:00:00+08:00",
        "timestamp_semantics": "published",
        "discovered_via": "api",
        "content_scope": "summary",
        "inline_content": "Candidate summary",
    }
    values.update(changes)
    return CandidateRecordV2.model_validate(values)


def _content(**changes: object) -> ExtractedDocumentV2:
    values: dict[str, object] = {
        "candidate_id": "candidate-1",
        "canonical_url": "https://news.example/read?id=1&utm_medium=rss#body",
        "title": "Extracted title",
        "text": "Extracted article body.",
        "content_hash": "a" * 64,
        "published_at": None,
        "extractor_version": "research-extractor/2.0",
    }
    values.update(changes)
    return ExtractedDocumentV2.model_validate(values)


def test_canonical_url_keeps_article_identity() -> None:
    first = canonicalize_url(
        "https://news.example/read?id=1&utm_source=test#top"
    )
    second = canonicalize_url("https://news.example/read?id=2")

    assert first == "https://news.example/read?id=1"
    assert first != second


def test_canonical_url_preserves_path_case_and_meaningful_query_order() -> None:
    value = canonicalize_url(
        "https://NEWS.example:443/Release/V2?lang=ZH&id=A%2FB&fbclid=x"
    )

    assert value == "https://news.example/Release/V2?lang=ZH&id=A%2FB"


def test_normalize_preserves_source_mapping_content_and_exact_times() -> None:
    document = normalize(_candidate(), _content())

    assert document.candidate_id == "candidate-1"
    assert document.source_item_id == "article-1"
    assert document.source_item_version == "v1"
    assert document.original_url.endswith("utm_source=test#top")
    assert document.canonical_url == "https://news.example/read?id=1"
    assert document.title == "Extracted title"
    assert document.text == "Extracted article body."
    assert document.content_scope == "summary"
    assert document.content_hash == "a" * 64
    assert document.published_at == datetime(2026, 9, 15, 2, tzinfo=UTC)
    assert document.first_published_at == datetime(2026, 9, 15, 1, tzinfo=UTC)
    assert document.updated_at == datetime(2026, 9, 15, 3, tzinfo=UTC)
    assert document.time_precision == "exact"
    assert document.published_timezone_known is True
    assert document.first_seen_at is None
    assert document.fetched_at is None


def test_date_without_timezone_remains_unknown_and_is_not_filled_with_now() -> None:
    document = normalize(
        _candidate(
            raw_published_at="2026-09-15",
            raw_created_at=None,
            raw_updated_at=None,
        ),
        _content(),
    )

    assert document.published_at is None
    assert document.published_interval_end is None
    assert document.time_precision == "day"
    assert document.published_timezone_known is False
    assert document.first_seen_at is None


def test_candidate_and_content_identity_mismatch_fails_closed() -> None:
    with pytest.raises(ValueError, match="NORMALIZATION_CANDIDATE_MISMATCH"):
        normalize(_candidate(), _content(candidate_id="candidate-2"))


@pytest.mark.parametrize(
    "value",
    [
        "http://news.example/a",
        "https://user:secret@news.example/a",
    ],
)
def test_unsafe_or_identity_empty_url_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="CANONICAL_URL_INVALID"):
        canonicalize_url(value)


def test_tracking_only_query_is_removed_when_path_identifies_resource() -> None:
    assert (
        canonicalize_url("https://news.example/a?utm_source=x&utm_medium=y#top")
        == "https://news.example/a"
    )
