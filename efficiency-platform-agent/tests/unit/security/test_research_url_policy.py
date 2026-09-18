"""研究 URL 授权策略的失败关闭测试。"""

from __future__ import annotations

import pytest

from efficiency_platform_agent.security.url_policy import (
    ResearchUrlSourcePolicy,
    UrlPolicy,
    UrlPolicyError,
)

PUBLIC_V4 = "93.184.216.34"
PUBLIC_V6 = "2606:2800:220:1:248:1893:25c8:1946"


def _policy(*hosts: str) -> ResearchUrlSourcePolicy:
    return ResearchUrlSourcePolicy(allowed_hosts=hosts)


@pytest.mark.parametrize(
    ("url", "ips"),
    [
        ("https://news.example.test/a", ("127.0.0.1",)),
        ("https://news.example.test/a", ("10.0.0.1",)),
        ("https://news.example.test/a", ("169.254.169.254",)),
        ("https://news.example.test/a", ("::1",)),
        ("https://news.example.test/a", ("fe80::1",)),
        ("https://news.example.test/a", ("::ffff:93.184.216.34",)),
        ("https://news.example.test/a", ("224.0.0.1",)),
        ("https://news.example.test/a", ("ff02::1",)),
        ("https://news.example.test/a", (PUBLIC_V4, "192.168.1.2")),
    ],
)
def test_non_public_or_mixed_resolution_is_rejected(
    url: str, ips: tuple[str, ...]
) -> None:
    with pytest.raises(UrlPolicyError, match="CONTENT_REJECTED"):
        UrlPolicy().authorize(url, _policy("news.example.test"), ips)


@pytest.mark.parametrize(
    "url",
    [
        "http://news.example.test/a",
        "https://user:secret@news.example.test/a",
        "https://news.example.test:8443/a",
        "https://localhost/a",
        "https://news.example.test.evil.invalid/a",
        "https://93.184.216.34/a",
        "https://news.example.test\\@evil.invalid/a",
    ],
)
def test_unsafe_url_shape_or_host_is_rejected(url: str) -> None:
    with pytest.raises(UrlPolicyError, match="CONTENT_REJECTED"):
        UrlPolicy().authorize(url, _policy("news.example.test"), (PUBLIC_V4,))


def test_exact_and_explicit_wildcard_hosts_have_distinct_semantics() -> None:
    policy = UrlPolicy()
    exact = _policy("example.test")
    wildcard = _policy("*.example.test")

    policy.authorize("https://example.test/a", exact, (PUBLIC_V4,))
    with pytest.raises(UrlPolicyError):
        policy.authorize("https://sub.example.test/a", exact, (PUBLIC_V4,))
    policy.authorize("https://sub.example.test/a", wildcard, (PUBLIC_V4,))
    with pytest.raises(UrlPolicyError):
        policy.authorize("https://example.test/a", wildcard, (PUBLIC_V4,))


def test_authorized_target_is_canonical_and_binds_verified_ip() -> None:
    target = UrlPolicy().authorize(
        "https://NEWS.example.test/path?q=1#fragment",
        _policy("news.example.test"),
        (PUBLIC_V6, PUBLIC_V4, PUBLIC_V4),
    )

    assert target.url == "https://news.example.test/path?q=1"
    assert target.host == "news.example.test"
    assert target.port == 443
    assert target.tls_server_name == "news.example.test"
    assert target.verified_ips == (PUBLIC_V6, PUBLIC_V4)
    assert target.connect_ip == PUBLIC_V6
    assert len(target.resolution_digest) == 64
