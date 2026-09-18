"""R08 GDELT URL 线索离线适配契约。"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import unquote

import pytest

from efficiency_platform_agent.contracts.research_sources_v2 import DiscoveryRequestV2
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from efficiency_platform_agent.providers.research.gdelt import (
    GdeltConfig,
    GdeltProvider,
)

from ._support import FakeDocumentFetcher, fetched


def _request(*, start: datetime | None = None) -> DiscoveryRequestV2:
    start_at = start or datetime(2026, 9, 15, tzinfo=UTC)
    return DiscoveryRequestV2(
        request_id="gdelt-request",
        source_id="fixture-gdelt",
        tenant_id="tenant-1",
        run_id="run-1",
        lease_id="lease-1",
        authorization_scope_digest="d" * 64,
        brief_digest="b" * 64,
        query="artificial intelligence",
        time_window=ResolvedTimeWindow(
            start=start_at,
            end=datetime(2026, 9, 17, tzinfo=UTC),
            timezone="UTC",
            precision="day",
            original_text="window",
            anchor=datetime(2026, 9, 17, tzinfo=UTC),
        ),
        limit=10,
    )


@pytest.mark.asyncio
async def test_gdelt_uses_explicit_window_and_returns_url_only_leads() -> None:
    config = GdeltConfig(
        "fixture-gdelt", earliest_supported_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    request = _request()
    url = GdeltProvider.build_url(config, request)
    body = b'{"articles":[{"url":"https://news.example/a?id=1","title":"AI event","seendate":"20260916T120000Z","domain":"news.example","language":"English","sourcecountry":"US"}]}'
    fetcher = FakeDocumentFetcher(
        {url: fetched(url=url, body=body, media_type="application/json")}
    )

    batch = await GdeltProvider(config, fetcher).discover(request)

    candidate = batch.candidates[0]
    assert candidate.raw_published_at is None
    assert candidate.raw_first_seen_at == "2026-09-16T12:00:00Z"
    assert candidate.content_scope == "none"
    assert candidate.inline_content is None
    assert "requires_content_fetch" in candidate.labels
    assert batch.completeness == "unknown"
    assert batch.coverage == "unknown"
    decoded = unquote(fetcher.requests[0].url)
    assert "startdatetime=20260915000000" in decoded
    assert "enddatetime=20260917000000" in decoded


@pytest.mark.asyncio
async def test_gdelt_unsupported_history_stops_before_fetch() -> None:
    config = GdeltConfig(
        "fixture-gdelt", earliest_supported_at=datetime(2026, 9, 1, tzinfo=UTC)
    )
    fetcher = FakeDocumentFetcher({})

    batch = await GdeltProvider(config, fetcher).discover(
        _request(start=datetime(2026, 8, 1, tzinfo=UTC))
    )

    assert fetcher.requests == []
    assert batch.attempts[0].error_code == "SOURCE_HISTORY_UNSUPPORTED"
    assert batch.coverage == "unknown"


@pytest.mark.asyncio
async def test_gdelt_malformed_200_is_schema_failure() -> None:
    config = GdeltConfig("fixture-gdelt")
    request = _request()
    url = GdeltProvider.build_url(config, request)
    fetcher = FakeDocumentFetcher(
        {url: fetched(url=url, body=b'{"articles":"bad"}', media_type="application/json")}
    )

    batch = await GdeltProvider(config, fetcher).discover(request)

    assert batch.attempts[0].error_code == "SOURCE_SCHEMA_INVALID"
