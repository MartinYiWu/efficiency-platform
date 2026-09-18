"""摘要、平台归属文本与全文许可不可互换。"""

import pytest

from efficiency_platform_agent.providers.research.arxiv import (
    ArxivConfig,
    ArxivProvider,
)
from efficiency_platform_agent.providers.research.feed import (
    FeedSourceConfig,
    FeedSourceProvider,
)
from efficiency_platform_agent.providers.research.github_releases import (
    GitHubReleasesConfig,
    GitHubReleasesProvider,
)
from efficiency_platform_agent.providers.research.hacker_news import (
    HackerNewsConfig,
    HackerNewsProvider,
)

from ._support import FakeDocumentFetcher, fetched
from .test_arxiv import _atom
from .test_arxiv import _request as arxiv_request
from .test_feed import FEED_URL, FIXTURES
from .test_feed import _request as feed_request
from .test_github_releases import _request as github_request
from .test_hacker_news import LIST_URL
from .test_hacker_news import _request as hn_request


@pytest.mark.parametrize("field", ["description", "content:encoded"])
async def test_feed_content_is_not_full_without_explicit_source_permission(field):
    body = f"""<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
    <channel><title>Source</title><item><guid>one</guid><title>Release</title>
    <link>https://example.test/article</link><{field}>Brief source text</{field}>
    </item></channel></rss>""".encode()
    fetcher = FakeDocumentFetcher(
        {FEED_URL: fetched(url=FEED_URL, body=body, media_type="application/rss+xml")}
    )
    batch = await FeedSourceProvider(
        FeedSourceConfig("fixture-feed", FEED_URL, history_mode="latest_only"), fetcher
    ).discover(feed_request())
    assert len(batch.candidates) == 1
    assert batch.candidates[0].content_scope == "summary"


async def test_release_body_is_only_attributed_platform_text():
    url = "https://api.github.com/repos/acme/widget/releases?page=1&per_page=2"
    fetcher = FakeDocumentFetcher(
        {
            url: fetched(
                url=url,
                body=(FIXTURES / "github_releases.json").read_bytes(),
                media_type="application/json",
            )
        }
    )
    batch = await GitHubReleasesProvider(
        GitHubReleasesConfig("fixture-github", "acme", "widget"), fetcher
    ).discover(github_request())
    assert batch.candidates[0].content_scope == "platform_text"
    assert "attributed_release_notes_only" in batch.candidates[0].labels


async def test_full_feed_content_requires_explicit_verified_body_policy():
    assert "body_content_scope" in FeedSourceConfig.__dataclass_fields__
    fetcher = FakeDocumentFetcher(
        {
            FEED_URL: fetched(
                url=FEED_URL,
                body=(FIXTURES / "atom.xml").read_bytes(),
                media_type="application/atom+xml",
            )
        }
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
    ).discover(feed_request())
    assert batch.candidates[0].content_scope == "full"


async def test_source_full_permission_cannot_upgrade_feed_description():
    assert "body_content_scope" in FeedSourceConfig.__dataclass_fields__
    fetcher = FakeDocumentFetcher(
        {
            FEED_URL: fetched(
                url=FEED_URL,
                body=(FIXTURES / "feed.xml").read_bytes(),
                media_type="application/rss+xml",
            )
        }
    )
    batch = await FeedSourceProvider(
        FeedSourceConfig(
            "fixture-feed", FEED_URL, history_mode="archive", body_content_scope="full"
        ),
        fetcher,
    ).discover(feed_request())
    assert batch.candidates[0].content_scope == "summary"


async def test_arxiv_abstract_cannot_be_article_fulltext():
    config = ArxivConfig("fixture-arxiv")
    request = arxiv_request()
    url = ArxivProvider.build_url(config, request)
    fetcher = FakeDocumentFetcher(
        {
            url: fetched(
                url=url,
                body=_atom(),
                media_type="application/atom+xml",
            )
        }
    )
    batch = await ArxivProvider(config, fetcher).discover(request)
    assert batch.candidates
    assert all(item.content_scope == "summary" for item in batch.candidates)


async def test_hn_external_link_does_not_grant_article_fulltext():
    url = "https://hacker-news.firebaseio.com/v0/item/9001.json"
    fetcher = FakeDocumentFetcher(
        {
            LIST_URL: fetched(
                url=LIST_URL, body=b"[9001]", media_type="application/json"
            ),
            url: fetched(
                url=url,
                body=(FIXTURES / "hn_item_9001.json").read_bytes(),
                media_type="application/json",
            ),
        }
    )
    batch = await HackerNewsProvider(HackerNewsConfig("fixture-hn"), fetcher).discover(
        hn_request(limit=1)
    )
    assert batch.candidates[0].content_scope == "none"
    assert len(fetcher.requests) == 2
