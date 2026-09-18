"""Hacker News 来源适配器契约。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from efficiency_platform_agent.contracts.research_sources_v2 import DiscoveryRequestV2
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from efficiency_platform_agent.providers.research.hacker_news import (
    HackerNewsConfig,
    HackerNewsProvider,
)

from ._support import FakeDocumentFetcher, fetched

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures/research_v2/providers"
LIST_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"


def _request(limit: int = 2) -> DiscoveryRequestV2:
    return DiscoveryRequestV2(
        request_id="hn-request",
        source_id="fixture-hn",
        tenant_id="tenant-1",
        run_id="run-1",
        lease_id="lease-1",
        authorization_scope_digest="d" * 64,
        brief_digest="c" * 64,
        query="AI",
        time_window=ResolvedTimeWindow(
            start=datetime(2026, 9, 15, tzinfo=UTC),
            end=datetime(2026, 9, 17, tzinfo=UTC),
            timezone="UTC",
            precision="day",
            original_text="recent",
            anchor=datetime(2026, 9, 16, tzinfo=UTC),
        ),
        limit=limit,
    )


@pytest.mark.asyncio
async def test_list_and_items_are_all_counted_and_semantics_are_explicit() -> None:
    responses = {
        LIST_URL: fetched(
            url=LIST_URL,
            body=(FIXTURES / "hn_topstories.json").read_bytes(),
            media_type="application/json",
        ),
        "https://hacker-news.firebaseio.com/v0/item/9001.json": fetched(
            url="https://hacker-news.firebaseio.com/v0/item/9001.json",
            body=(FIXTURES / "hn_item_9001.json").read_bytes(),
            media_type="application/json",
        ),
        "https://hacker-news.firebaseio.com/v0/item/9002.json": fetched(
            url="https://hacker-news.firebaseio.com/v0/item/9002.json",
            body=(FIXTURES / "hn_item_9002.json").read_bytes(),
            media_type="application/json",
        ),
    }
    fetcher = FakeDocumentFetcher(responses, delay_seconds=0.01)
    batch = await HackerNewsProvider(
        HackerNewsConfig("fixture-hn", max_concurrency=2), fetcher
    ).discover(_request())

    assert batch.attempts[0].usage.requests == 3
    assert len(fetcher.requests) == 3
    assert fetcher.max_active == 2
    assert batch.candidates[0].timestamp_semantics == "platform_posted"
    assert "hn_score=42" in (batch.candidates[0].heat_observation or "")
    assert batch.candidates[1].raw_published_at is None
    assert batch.candidates[1].content_scope == "platform_text"
    assert batch.coverage == "unknown"
    assert batch.completeness == "truncated"


@pytest.mark.asyncio
async def test_partial_item_failure_keeps_other_candidates_and_is_truncated() -> None:
    responses = {
        LIST_URL: fetched(
            url=LIST_URL,
            body=b"[9001,9002]",
            media_type="application/json",
        ),
        "https://hacker-news.firebaseio.com/v0/item/9001.json": fetched(
            url="https://hacker-news.firebaseio.com/v0/item/9001.json",
            body=(FIXTURES / "hn_item_9001.json").read_bytes(),
            media_type="application/json",
        ),
        "https://hacker-news.firebaseio.com/v0/item/9002.json": fetched(
            url="https://hacker-news.firebaseio.com/v0/item/9002.json",
            body=b"not-json",
            media_type="application/json",
        ),
    }
    batch = await HackerNewsProvider(
        HackerNewsConfig("fixture-hn", max_concurrency=2),
        FakeDocumentFetcher(responses),
    ).discover(_request())

    assert len(batch.candidates) == 1
    assert batch.attempts[0].status == "truncated"
    assert batch.attempts[0].error_code == "SOURCE_SCHEMA_INVALID"


@pytest.mark.asyncio
async def test_invalid_list_200_is_failure() -> None:
    fetcher = FakeDocumentFetcher(
        {LIST_URL: fetched(url=LIST_URL, body=b"{}", media_type="application/json")}
    )
    batch = await HackerNewsProvider(
        HackerNewsConfig("fixture-hn"), fetcher
    ).discover(_request())
    assert batch.attempts[0].status == "failed"
    assert batch.attempts[0].error_code == "SOURCE_SCHEMA_INVALID"
