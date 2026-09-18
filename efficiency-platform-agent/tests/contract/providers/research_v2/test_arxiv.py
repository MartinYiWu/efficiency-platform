"""R08 arXiv 元数据/摘要离线适配契约。"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import unquote

import pytest

from efficiency_platform_agent.contracts.research_sources_v2 import DiscoveryRequestV2
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from efficiency_platform_agent.providers.research.arxiv import (
    ArxivConfig,
    ArxivProvider,
)

from ._support import FakeDocumentFetcher, fetched


def _request(*, cursor: str | None = None) -> DiscoveryRequestV2:
    return DiscoveryRequestV2(
        request_id="arxiv-request",
        source_id="fixture-arxiv",
        tenant_id="tenant-1",
        run_id="run-1",
        lease_id="lease-1",
        authorization_scope_digest="d" * 64,
        brief_digest="b" * 64,
        query="large language model",
        time_window=ResolvedTimeWindow(
            start=datetime(2026, 9, 1, tzinfo=UTC),
            end=datetime(2026, 9, 17, tzinfo=UTC),
            timezone="UTC",
            precision="day",
            original_text="September",
            anchor=datetime(2026, 9, 17, tzinfo=UTC),
        ),
        cursor=cursor,
        limit=2,
    )


def _atom() -> bytes:
    return b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>3</opensearch:totalResults>
  <entry><id>https://arxiv.org/abs/2609.00001v2</id><updated>2026-09-16T10:00:00Z</updated><published>2026-09-15T08:00:00Z</published><title> A safe model </title><summary> Abstract evidence only. </summary><category term="cs.AI"/><link href="https://arxiv.org/pdf/2609.00001v2" type="application/pdf"/></entry>
</feed>'''


@pytest.mark.asyncio
async def test_arxiv_has_explicit_window_pagination_and_abstract_scope() -> None:
    config = ArxivConfig("fixture-arxiv", categories=("cs.AI",))
    request = _request()
    url = ArxivProvider.build_url(config, request)
    fetcher = FakeDocumentFetcher(
        {url: fetched(url=url, body=_atom(), media_type="application/atom+xml")}
    )

    batch = await ArxivProvider(config, fetcher).discover(request)

    assert len(batch.candidates) == 1
    candidate = batch.candidates[0]
    assert candidate.url == "https://arxiv.org/abs/2609.00001v2"
    assert candidate.raw_published_at == "2026-09-15T08:00:00Z"
    assert candidate.raw_updated_at == "2026-09-16T10:00:00Z"
    assert candidate.content_scope == "summary"
    assert candidate.inline_content == "Abstract evidence only."
    assert "abstract_only" in candidate.labels
    assert batch.next_cursor == "2"
    assert batch.completeness == "truncated"
    decoded = unquote(fetcher.requests[0].url)
    assert "submittedDate:[202609010000 TO 202609170000]" in decoded
    assert "cat:cs.AI" in decoded


@pytest.mark.asyncio
async def test_arxiv_malformed_200_is_schema_failure() -> None:
    config = ArxivConfig("fixture-arxiv")
    request = _request()
    url = ArxivProvider.build_url(config, request)
    fetcher = FakeDocumentFetcher(
        {url: fetched(url=url, body=b"<feed><entry>", media_type="application/atom+xml")}
    )

    batch = await ArxivProvider(config, fetcher).discover(request)

    assert batch.candidates == ()
    assert batch.attempts[0].error_code == "SOURCE_SCHEMA_INVALID"
    assert batch.coverage == "unknown"
