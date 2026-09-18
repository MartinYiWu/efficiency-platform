"""研究采集 URL 的确定性授权与 DNS 结果门禁。"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from urllib.parse import SplitResult, urlsplit, urlunsplit

from efficiency_platform_agent.contracts.research_transport_v2 import (
    AuthorizedTargetV2,
    ResearchUrlSourcePolicyV2,
    UrlTargetShapeV2,
)


class UrlPolicyError(ValueError):
    """URL 无法安全授权时返回的稳定拒绝。"""

    code = "CONTENT_REJECTED"

    def __init__(self, reason_code: str) -> None:
        super().__init__(self.code)
        self.reason_code = reason_code


ResearchUrlSourcePolicy = ResearchUrlSourcePolicyV2
AuthorizedTarget = AuthorizedTargetV2
TargetShape = UrlTargetShapeV2


class UrlPolicy:
    """在连接前校验 URL 形状、来源 host 和全部解析地址。"""

    def authorize(
        self,
        url: str,
        source_policy: ResearchUrlSourcePolicyV2,
        resolved_ips: tuple[str, ...],
    ) -> AuthorizedTargetV2:
        source_policy = _normalize_source_policy(source_policy)
        shape = self.validate_shape(url, source_policy)
        verified = _verify_public_ips(resolved_ips)
        digest_value = "\n".join(
            (shape.host, str(shape.port), *verified)
        ).encode("ascii")
        return AuthorizedTargetV2(
            url=shape.url,
            host=shape.host,
            port=shape.port,
            verified_ips=verified,
            connect_ip=verified[0],
            tls_server_name=shape.host,
            resolution_digest=hashlib.sha256(digest_value).hexdigest(),
        )

    def validate_shape(
        self, url: str, source_policy: ResearchUrlSourcePolicyV2
    ) -> UrlTargetShapeV2:
        """在任何 DNS 操作前拒绝未授权 URL。"""
        source_policy = _normalize_source_policy(source_policy)
        if not isinstance(url, str) or any(
            ord(character) < 32 or ord(character) == 127 for character in url
        ):
            raise UrlPolicyError("URL_MALFORMED")
        if "\\" in url:
            raise UrlPolicyError("URL_BACKSLASH_FORBIDDEN")
        try:
            split = urlsplit(url)
            port = split.port or 443
        except (TypeError, ValueError) as exc:
            raise UrlPolicyError("URL_MALFORMED") from exc
        if split.scheme.lower() != "https":
            raise UrlPolicyError("URL_SCHEME_FORBIDDEN")
        if split.username is not None or split.password is not None:
            raise UrlPolicyError("URL_USERINFO_FORBIDDEN")
        if not split.hostname:
            raise UrlPolicyError("URL_HOST_MISSING")
        host = _normalize_hostname(split.hostname)
        if host == "localhost" or host.endswith(".localhost"):
            raise UrlPolicyError("URL_LOCALHOST_FORBIDDEN")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise UrlPolicyError("URL_IP_LITERAL_FORBIDDEN")
        if port not in source_policy.allowed_ports:
            raise UrlPolicyError("URL_PORT_FORBIDDEN")
        if not any(_host_matches(host, item) for item in source_policy.allowed_hosts):
            raise UrlPolicyError("URL_HOST_FORBIDDEN")
        canonical_url = urlunsplit(
            SplitResult("https", host, split.path or "/", split.query, "")
        )
        return UrlTargetShapeV2(
            url=canonical_url,
            host=host,
            port=port,
        )


def _normalize_source_policy(
    source_policy: ResearchUrlSourcePolicyV2,
) -> ResearchUrlSourcePolicyV2:
    if not isinstance(source_policy, ResearchUrlSourcePolicyV2):
        raise TypeError("source_policy 类型不正确")
    if not source_policy.allowed_hosts or not source_policy.allowed_ports:
        raise ValueError("URL_SOURCE_POLICY_EMPTY")
    normalized = tuple(
        _normalize_host_pattern(item) for item in source_policy.allowed_hosts
    )
    if len(set(normalized)) != len(normalized):
        raise ValueError("URL_SOURCE_POLICY_DUPLICATED")
    if any(port != 443 for port in source_policy.allowed_ports):
        raise ValueError("URL_SOURCE_POLICY_INSECURE_PORT")
    if normalized == source_policy.allowed_hosts:
        return source_policy
    return ResearchUrlSourcePolicyV2(normalized, source_policy.allowed_ports)


def _normalize_host_pattern(value: str) -> str:
    candidate = value.strip().lower().rstrip(".")
    wildcard = candidate.startswith("*.")
    host = candidate[2:] if wildcard else candidate
    normalized = _normalize_hostname(host)
    if not normalized or "*" in normalized:
        raise ValueError("URL_SOURCE_HOST_INVALID")
    return f"*.{normalized}" if wildcard else normalized


def _normalize_hostname(value: str) -> str:
    candidate = value.strip().lower().rstrip(".")
    if not candidate or "%" in candidate:
        raise UrlPolicyError("URL_HOST_INVALID")
    try:
        normalized = candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UrlPolicyError("URL_HOST_INVALID") from exc
    if len(normalized) > 253 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in normalized.split(".")
    ):
        raise UrlPolicyError("URL_HOST_INVALID")
    return normalized


def _host_matches(host: str, pattern: str) -> bool:
    if pattern.startswith("*."):
        suffix = pattern[1:]
        return host.endswith(suffix) and host != pattern[2:]
    return host == pattern


def _verify_public_ips(values: tuple[str, ...]) -> tuple[str, ...]:
    if not values:
        raise UrlPolicyError("DNS_EMPTY")
    verified: list[str] = []
    for value in values:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise UrlPolicyError("DNS_ADDRESS_INVALID") from exc
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            raise UrlPolicyError("DNS_MAPPED_ADDRESS_FORBIDDEN")
        if (
            not address.is_global
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
            or address.is_loopback
            or address.is_link_local
            or address.is_private
        ):
            raise UrlPolicyError("DNS_NON_PUBLIC_ADDRESS")
        canonical = address.compressed
        if canonical not in verified:
            verified.append(canonical)
    return tuple(verified)


__all__ = [
    "AuthorizedTarget",
    "ResearchUrlSourcePolicy",
    "TargetShape",
    "UrlPolicy",
    "UrlPolicyError",
]
