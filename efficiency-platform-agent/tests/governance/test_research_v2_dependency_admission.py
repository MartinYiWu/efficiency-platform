"""研究 V2 解析依赖的离线准入测试。"""

from datetime import datetime
from zoneinfo import ZoneInfo

import dateparser
import feedparser
import httpx
import trafilatura


def test_rss_and_atom_parse_from_memory() -> None:
    rss = feedparser.parse(b"<rss version='2.0'><channel><title>News</title><item><title>One</title></item></channel></rss>")
    atom = feedparser.parse(b"<feed xmlns='http://www.w3.org/2005/Atom'><title>News</title><entry><title>Two</title></entry></feed>")
    assert rss.entries[0].title == "One"
    assert atom.entries[0].title == "Two"


def test_html_body_extracts_without_network() -> None:
    html = "<html><body><main><article><h1>发布公告</h1><p>这是一段足够完整的正文内容，介绍产品发布的具体细节与背景。</p></article></main></body></html>"
    result = trafilatura.extract(html)
    assert result is not None
    assert "产品发布" in result


def test_chinese_relative_date_has_explicit_base_and_timezone() -> None:
    base = datetime(2026, 9, 16, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    result = dateparser.parse(
        "昨天",
        languages=["zh"],
        settings={"RELATIVE_BASE": base, "TIMEZONE": "Asia/Shanghai", "RETURN_AS_TIMEZONE_AWARE": True},
    )
    assert result is not None
    assert result.date().isoformat() == "2026-09-15"
    assert result.utcoffset() == base.utcoffset()


def test_runtime_httpx_and_iana_timezone_available() -> None:
    assert httpx.__version__
    assert ZoneInfo("Asia/Shanghai").key == "Asia/Shanghai"
