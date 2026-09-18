"""研究传输授权目标的中立契约。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResearchUrlSourcePolicyV2:
    """来源允许的主机模式与 HTTPS 端口。"""

    allowed_hosts: tuple[str, ...]
    allowed_ports: frozenset[int] = frozenset({443})


@dataclass(frozen=True, slots=True)
class UrlTargetShapeV2:
    """URL 形状和来源 host 已校验、DNS 尚未授权的目标。"""

    url: str
    host: str
    port: int


@dataclass(frozen=True, slots=True)
class AuthorizedTargetV2:
    """仅可由安全策略生成的受限连接描述。"""

    url: str
    host: str
    port: int
    verified_ips: tuple[str, ...]
    connect_ip: str
    tls_server_name: str
    resolution_digest: str


__all__ = [
    "AuthorizedTargetV2",
    "ResearchUrlSourcePolicyV2",
    "UrlTargetShapeV2",
]
