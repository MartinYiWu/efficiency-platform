"""RSS/Atom 来源适配器契约。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from efficiency_platform_agent.contracts.research_sources_v2 import (
    DiscoveryRequestV2,
    FetchRequestV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from efficiency_platform_agent.providers.research.cache import (
    ConditionalDocumentFetcher,
    InMemoryResponseCache,
)
from efficiency_platform_agent.providers.research.feed import (
    FeedSourceConfig,
    FeedSourceProvider,
)
from efficiency_platform_agent.providers.research.transport import ResearchFetchError

from ._support import FakeDocumentFetcher, fetched

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures/research_v2/providers"
FEED_URL = "https://feeds.example.test/latest.xml"


def _request(*, limit: int = 20, cursor: str | None = None) -> DiscoveryRequestV2:
    return DiscoveryRequestV2(
        request_id="feed-request",
        source_id="fixture-feed",
        tenant_id="tenant-1",
        run_id="run-1",
        lease_id="lease-1",
        authorization_scope_digest="d" * 64,
        brief_digest="a" * 64,
        query="AI release",
        time_window=ResolvedTimeWindow(
            start=datetime(2026, 9, 8, tzinfo=UTC),
            end=datetime(2026, 9, 15, tzinfo=UTC),
            timezone="UTC",
            precision="day",
            original_text="last week",
            anchor=datetime(2026, 9, 16, tzinfo=UTC),
        ),
        cursor=cursor,
        limit=limit,
    )


@pytest.mark.asyncio
async def test_feed_preserves_ids_dates_content_scope_and_unknown_history() -> None:
    body = (FIXTURES / "feed.xml").read_bytes()
    fetcher = FakeDocumentFetcher(
        {FEED_URL: fetched(url=FEED_URL, body=body, media_type="application/rss+xml")}
    )
    provider = FeedSourceProvider(
        FeedSourceConfig("fixture-feed", FEED_URL, history_mode="latest_only"),
        fetcher,
    )

    batch = await provider.discover(_request())

    assert [item.source_item_id for item in batch.candidates] == [
        "release-1",
        "release-2",
    ]
    assert batch.candidates[0].raw_published_at == "Tue, 15 Sep 2026 01:00:00 GMT"
    assert batch.candidates[0].content_scope == "summary"
    assert batch.candidates[0].inline_content == "Summary one"
    assert batch.candidates[1].raw_published_at is None
    assert batch.coverage == "unknown"
    assert batch.attempts[0].status == "success"
    assert batch.attempts[0].usage.requests == 1


@pytest.mark.asyncio
async def test_empty_feed_is_success_empty_not_failure() -> None:
    body = (FIXTURES / "feed_empty.xml").read_bytes()
    fetcher = FakeDocumentFetcher(
        {FEED_URL: fetched(url=FEED_URL, body=body, media_type="application/rss+xml")}
    )
    batch = await FeedSourceProvider(
        FeedSourceConfig("fixture-feed", FEED_URL, history_mode="latest_only"),
        fetcher,
    ).discover(_request())

    assert batch.candidates == ()
    assert batch.attempts[0].status == "success_empty"
    assert batch.coverage == "unknown"


@pytest.mark.asyncio
async def test_malformed_200_and_bare_304_are_failures() -> None:
    invalid = FakeDocumentFetcher(
        {
            FEED_URL: fetched(
                url=FEED_URL, body=b"not xml", media_type="application/rss+xml"
            )
        }
    )
    invalid_batch = await FeedSourceProvider(
        FeedSourceConfig("fixture-feed", FEED_URL, history_mode="latest_only"),
        invalid,
    ).discover(_request())
    not_modified = FakeDocumentFetcher(
        {
            FEED_URL: fetched(
                url=FEED_URL,
                body=b"",
                media_type="application/rss+xml",
                status_code=304,
            )
        }
    )
    not_modified_batch = await FeedSourceProvider(
        FeedSourceConfig("fixture-feed", FEED_URL, history_mode="latest_only"),
        not_modified,
    ).discover(_request())

    assert invalid_batch.attempts[0].error_code == "SOURCE_SCHEMA_INVALID"
    assert not_modified_batch.attempts[0].error_code == "CONTENT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_feed_cursor_is_bounded_and_truncation_is_explicit() -> None:
    body = (FIXTURES / "feed.xml").read_bytes()
    fetcher = FakeDocumentFetcher(
        {FEED_URL: fetched(url=FEED_URL, body=body, media_type="application/rss+xml")}
    )
    provider = FeedSourceProvider(
        FeedSourceConfig("fixture-feed", FEED_URL, history_mode="archive"), fetcher
    )

    first = await provider.discover(_request(limit=1))
    second = await provider.discover(_request(limit=1, cursor=first.next_cursor))

    assert first.completeness == "truncated"
    assert first.next_cursor == "1"
    assert second.candidates[0].source_item_id == "release-2"
    assert second.next_cursor is None


@pytest.mark.asyncio
async def test_atom_full_content_and_updated_time_are_not_downgraded() -> None:
    body = (FIXTURES / "atom.xml").read_bytes()
    fetcher = FakeDocumentFetcher(
        {FEED_URL: fetched(url=FEED_URL, body=body, media_type="application/atom+xml")}
    )
    batch = await FeedSourceProvider(
        FeedSourceConfig(
            "fixture-feed",
            FEED_URL,
            history_mode="archive",
            access_mode="atom",
            body_content_scope="full",
        ),
        fetcher,
    ).discover(_request())

    assert batch.candidates[0].content_scope == "full"
    assert batch.candidates[0].inline_content == "Full Atom body"
    assert batch.candidates[0].raw_published_at is None
    assert batch.candidates[0].raw_updated_at == "2026-09-16T02:00:00Z"
    assert batch.candidates[0].timestamp_semantics == "updated"


@pytest.mark.asyncio
async def test_304_requires_same_tenant_authorization_and_unexpired_cache() -> None:
    cached_at = datetime(2026, 9, 16, tzinfo=UTC)
    body = (FIXTURES / "feed.xml").read_bytes()
    request = FetchRequestV2(
        request_id="cache-request-1",
        source_id="fixture-feed",
        tenant_id="tenant-1",
        run_id="run-1",
        lease_id="lease-1",
        authorization_scope_digest="d" * 64,
        candidate_id="feed-document",
        url=FEED_URL,
    )
    first_upstream = FakeDocumentFetcher(
        {
            FEED_URL: fetched(
                url=FEED_URL,
                body=body,
                media_type="application/rss+xml",
            ).model_copy(update={"etag": '"v1"'})
        }
    )
    store = InMemoryResponseCache()
    first = ConditionalDocumentFetcher(
        first_upstream,
        store,
        cache_version="feed-cache/1",
        clock=lambda: cached_at,
    )
    await first.fetch(request)
    not_modified = fetched(
        url=FEED_URL,
        body=b"",
        media_type="application/rss+xml",
        status_code=304,
    )
    second_upstream = FakeDocumentFetcher({FEED_URL: not_modified})
    second = ConditionalDocumentFetcher(
        second_upstream,
        store,
        cache_version="feed-cache/1",
        clock=lambda: cached_at,
    )

    result = await second.fetch(
        request.model_copy(update={"request_id": "cache-request-2"})
    )

    assert result.body == body
    assert result.cache_status == "revalidated"
    assert second_upstream.requests[0].etag == '"v1"'

    foreign_request = request.model_copy(
        update={"tenant_id": "tenant-2", "request_id": "cache-request-3"}
    )
    with pytest.raises(ResearchFetchError, match="CONTENT_UNAVAILABLE"):
        await second.fetch(foreign_request)

    expired_upstream = FakeDocumentFetcher({FEED_URL: not_modified})
    expired = ConditionalDocumentFetcher(
        expired_upstream,
        store,
        cache_version="feed-cache/1",
        clock=lambda: cached_at + timedelta(minutes=16),
    )
    with pytest.raises(ResearchFetchError, match="CONTENT_UNAVAILABLE"):
        await expired.fetch(
            request.model_copy(update={"request_id": "cache-request-4"})
        )
    assert expired_upstream.requests[0].etag is None
