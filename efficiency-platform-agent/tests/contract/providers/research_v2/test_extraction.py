"""离线正文与 Feed 解析边界测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from efficiency_platform_agent.contracts.research_sources_v2 import FetchedContentV2
from efficiency_platform_agent.providers.research._process_isolation import (
    IsolatedParseTimeout,
    run_isolated_parser,
)
from efficiency_platform_agent.providers.research.extraction import (
    DocumentExtractionError,
    DocumentExtractor,
)
from efficiency_platform_agent.providers.research.feed import SafeFeedParser


def _content(body: bytes, media_type: str, url: str = "https://news.test/a"):
    return FetchedContentV2(
        request_id="request-1",
        candidate_id="candidate-1",
        final_url=url,
        media_type=media_type,
        body=body,
        downloaded_bytes=len(body),
        fetched_at=datetime.now(UTC),
        status_code=200,
    )


def test_html_extractor_only_receives_downloaded_text() -> None:
    calls: list[str] = []

    def offline_extract(value: str) -> str:
        calls.append(value)
        assert not value.startswith("http")
        return "Article body"

    content = _content(
        b"<html><head><title>Example</title></head><body>Body</body></html>",
        "text/html",
        "https://news.test/final",
    )
    document = DocumentExtractor(
        html_extractor=offline_extract,
        allow_in_process_test_parser=True,
    ).extract(content)

    assert calls == [content.body.decode()]
    assert document.canonical_url == "https://news.test/final"
    assert document.title == "Example"
    assert document.text == "Article body"
    assert len(document.content_hash) == 64
    assert document.extractor_version.startswith("research-extractor/")


@pytest.mark.parametrize(
    ("media_type", "body", "expected_title"),
    [
        ("text/plain", b"First line\nSecond line", "First line"),
        ("application/json", b'{"title":"JSON title","value":3}', "JSON title"),
        ("application/xml", b"<root><title>XML title</title><p>Text</p></root>", "XML title"),
    ],
)
def test_supported_in_memory_formats_are_extracted(
    media_type: str, body: bytes, expected_title: str
) -> None:
    document = DocumentExtractor().extract(_content(body, media_type))
    assert document.title == expected_title
    assert document.text


@pytest.mark.parametrize(
    "body",
    [
        b'<!DOCTYPE x [<!ENTITY e "boom">]><x>&e;</x>',
        (b"<x>" * 40) + b"v" + (b"</x>" * 40),
    ],
)
def test_unsafe_xml_is_rejected_before_feedparser(body: bytes) -> None:
    called = False

    def parser(_: bytes):
        nonlocal called
        called = True
        return {}

    with pytest.raises(DocumentExtractionError, match="CONTENT_REJECTED"):
        SafeFeedParser(
            parser=parser,
            max_depth=16,
            allow_in_process_test_parser=True,
        ).parse(body)
    assert called is False


def test_feedparser_receives_bytes_not_url() -> None:
    observed: list[bytes] = []

    def parser(value: bytes):
        observed.append(value)
        return {"feed": {"title": "Feed"}, "entries": []}

    body = b"<rss><channel><title>Feed</title></channel></rss>"
    result = SafeFeedParser(
        parser=parser, allow_in_process_test_parser=True
    ).parse(body)

    assert observed == [body]
    assert result.title == "Feed"
    assert result.entry_count == 0


def test_parser_failures_are_mapped_to_stable_errors() -> None:
    def broken_feed(_: bytes):
        raise RuntimeError("secret parser detail")

    def broken_html(_: str) -> str:
        raise RuntimeError("secret extractor detail")

    feed_body = b"<rss><channel><title>Feed</title></channel></rss>"
    with pytest.raises(DocumentExtractionError, match="SOURCE_SCHEMA_INVALID"):
        SafeFeedParser(
            parser=broken_feed, allow_in_process_test_parser=True
        ).parse(feed_body)
    with pytest.raises(DocumentExtractionError, match="CONTENT_UNAVAILABLE"):
        DocumentExtractor(
            html_extractor=broken_html,
            allow_in_process_test_parser=True,
        ).extract(
            _content(b"<html><title>T</title><body>B</body></html>", "text/html")
        )


def test_custom_parser_requires_explicit_test_only_opt_in() -> None:
    with pytest.raises(ValueError, match="IN_PROCESS_TEST_PARSER_NOT_ALLOWED"):
        DocumentExtractor(html_extractor=lambda value: value)
    with pytest.raises(ValueError, match="IN_PROCESS_TEST_PARSER_NOT_ALLOWED"):
        SafeFeedParser(parser=lambda body: {"body": body})


def test_default_third_party_parsers_run_in_terminable_process() -> None:
    html = _content(
        b"<html><head><title>Safe</title></head><body><p>Article text.</p></body></html>",
        "text/html",
    )
    document = DocumentExtractor(parse_timeout_seconds=5.0).extract(html)
    feed = SafeFeedParser(parse_timeout_seconds=5.0).parse(
        b"<rss><channel><title>Feed</title></channel></rss>"
    )

    assert document.text == "Article text."
    assert feed.title == "Feed"


def test_isolated_parser_can_be_hard_stopped() -> None:
    with pytest.raises(IsolatedParseTimeout):
        run_isolated_parser("html", "<p>text</p>", timeout_seconds=1e-9)


def test_empty_or_unsupported_document_is_rejected() -> None:
    with pytest.raises(DocumentExtractionError, match="CONTENT_UNAVAILABLE"):
        DocumentExtractor().extract(_content(b"  ", "text/plain"))
    with pytest.raises(DocumentExtractionError, match="CONTENT_REJECTED"):
        DocumentExtractor().extract(_content(b"%PDF", "application/pdf"))
