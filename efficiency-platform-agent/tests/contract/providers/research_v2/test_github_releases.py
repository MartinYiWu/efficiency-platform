"""GitHub Releases 来源适配器契约。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from efficiency_platform_agent.contracts.research_sources_v2 import DiscoveryRequestV2
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from efficiency_platform_agent.providers.research.github_releases import (
    GitHubReleasesConfig,
    GitHubReleasesProvider,
)
from efficiency_platform_agent.providers.research.transport import ResearchFetchError

from ._support import FakeDocumentFetcher, fetched

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures/research_v2/providers"


def _request(*, cursor: str | None = None, limit: int = 2) -> DiscoveryRequestV2:
    return DiscoveryRequestV2(
        request_id="github-request",
        source_id="fixture-github",
        tenant_id="tenant-1",
        run_id="run-1",
        lease_id="lease-1",
        authorization_scope_digest="d" * 64,
        brief_digest="b" * 64,
        query="release",
        time_window=ResolvedTimeWindow(
            start=datetime(2026, 9, 1, tzinfo=UTC),
            end=datetime(2026, 9, 17, tzinfo=UTC),
            timezone="UTC",
            precision="day",
            original_text="September",
            anchor=datetime(2026, 9, 16, tzinfo=UTC),
        ),
        cursor=cursor,
        limit=limit,
    )


@pytest.mark.asyncio
async def test_releases_exclude_drafts_and_mark_prerelease_and_pagination() -> None:
    url = "https://api.github.com/repos/acme/widget/releases?page=1&per_page=2"
    body = (FIXTURES / "github_releases.json").read_bytes()
    fetcher = FakeDocumentFetcher(
        {
            url: fetched(
                url=url,
                body=body,
                media_type="application/json",
                headers=(
                    ("link", '<https://api.github.com/x?page=2>; rel="next"'),
                    ("x-ratelimit-remaining", "59"),
                ),
            )
        }
    )
    provider = GitHubReleasesProvider(
        GitHubReleasesConfig("fixture-github", "acme", "widget"), fetcher
    )

    batch = await provider.discover(_request())

    assert len(batch.candidates) == 2
    assert all("draft" not in item.labels for item in batch.candidates)
    assert "prerelease" in batch.candidates[1].labels
    assert batch.candidates[0].source_item_version == "v2.0.0"
    assert batch.candidates[1].raw_published_at is None
    assert batch.candidates[1].raw_created_at == "2026-09-16T08:00:00Z"
    assert batch.next_cursor == "2"
    assert batch.completeness == "truncated"
    assert batch.attempts[0].usage.requests == 1
    assert batch.attempts[0].rate_limit_remaining == 59


@pytest.mark.asyncio
async def test_invalid_200_is_failed_not_success_empty() -> None:
    url = "https://api.github.com/repos/acme/widget/releases?page=1&per_page=2"
    fetcher = FakeDocumentFetcher(
        {url: fetched(url=url, body=b'{"message":"oops"}', media_type="application/json")}
    )
    batch = await GitHubReleasesProvider(
        GitHubReleasesConfig("fixture-github", "acme", "widget"), fetcher
    ).discover(_request())

    assert batch.candidates == ()
    assert batch.attempts[0].status == "failed"
    assert batch.attempts[0].error_code == "SOURCE_SCHEMA_INVALID"
    assert batch.coverage == "unknown"


@pytest.mark.asyncio
async def test_403_and_429_reasons_are_preserved() -> None:
    url = "https://api.github.com/repos/acme/widget/releases?page=1&per_page=2"
    for status, error in ((403, "SOURCE_FORBIDDEN"), (429, "SOURCE_RATE_LIMITED")):
        fetcher = FakeDocumentFetcher(
            {url: fetched(url=url, body=b"{}", media_type="application/json", status_code=status)}
        )
        batch = await GitHubReleasesProvider(
            GitHubReleasesConfig("fixture-github", "acme", "widget"), fetcher
        ).discover(_request())
        assert batch.attempts[0].error_code == error


@pytest.mark.asyncio
async def test_429_retry_after_is_preserved_for_executor_backoff() -> None:
    url = "https://api.github.com/repos/acme/widget/releases?page=1&per_page=2"
    fetcher = FakeDocumentFetcher(
        {
            url: fetched(
                url=url,
                body=b"{}",
                media_type="application/json",
                status_code=429,
                headers=(("retry-after", "7"),),
            )
        }
    )

    batch = await GitHubReleasesProvider(
        GitHubReleasesConfig("fixture-github", "acme", "widget"), fetcher
    ).discover(_request())

    assert batch.attempts[0].error_code == "SOURCE_RATE_LIMITED"
    assert batch.attempts[0].retry_after_seconds == 7


@pytest.mark.asyncio
async def test_transport_429_metadata_is_preserved_in_failed_attempt() -> None:
    url = "https://api.github.com/repos/acme/widget/releases?page=1&per_page=2"
    fetcher = FakeDocumentFetcher(
        {
            url: ResearchFetchError(
                "CONTENT_UNAVAILABLE",
                "SOURCE_RATE_LIMITED",
                http_status=429,
                response_headers=(
                    ("retry-after", "9"),
                    ("x-ratelimit-remaining", "0"),
                ),
                downloaded_bytes=12,
            )
        }
    )

    batch = await GitHubReleasesProvider(
        GitHubReleasesConfig("fixture-github", "acme", "widget"), fetcher
    ).discover(_request())
    attempt = batch.attempts[0]

    assert attempt.error_code == "SOURCE_RATE_LIMITED"
    assert attempt.http_status == 429
    assert attempt.retry_after_seconds == 9
    assert attempt.rate_limit_remaining == 0
    assert attempt.usage.downloaded_bytes == 12
