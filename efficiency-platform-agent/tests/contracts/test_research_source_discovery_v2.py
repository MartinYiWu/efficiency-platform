"""研究发现与缓存范围扩展契约。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.research_sources_v2 import (
    CandidateRecordV2,
    FetchedContentV2,
)


def _candidate(**updates: object) -> CandidateRecordV2:
    payload: dict[str, object] = {
        "candidate_id": "candidate-1",
        "source_id": "source-1",
        "source_item_id": "item-1",
        "url": "https://news.example.test/a",
        "title": "Title",
        "discovered_via": "rss",
    }
    payload.update(updates)
    return CandidateRecordV2.model_validate(payload)


def test_inline_content_and_scope_cannot_disagree() -> None:
    with pytest.raises(ValidationError, match="CANDIDATE_CONTENT_SCOPE_INVALID"):
        _candidate(inline_content="body")
    with pytest.raises(ValidationError, match="CANDIDATE_INLINE_CONTENT_REQUIRED"):
        _candidate(content_scope="full")


def test_response_header_control_characters_are_rejected() -> None:
    with pytest.raises(ValidationError, match="FETCHED_RESPONSE_HEADERS_INVALID"):
        FetchedContentV2(
            request_id="request-1",
            candidate_id="candidate-1",
            final_url="https://news.example.test/a",
            media_type="text/plain",
            body=b"body",
            downloaded_bytes=4,
            fetched_at=datetime.now(UTC),
            status_code=200,
            response_headers=(("link", "safe\r\ninjected: true"),),
        )


def test_platform_timestamp_is_not_implicitly_a_publication_timestamp() -> None:
    candidate = _candidate(
        raw_published_at="2026-09-16T00:00:00Z",
        timestamp_semantics="platform_posted",
    )
    assert candidate.timestamp_semantics == "platform_posted"
