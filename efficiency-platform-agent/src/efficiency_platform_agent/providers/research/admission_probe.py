"""X04 来源准入使用的安全、一次性只读探针。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from efficiency_platform_agent.contracts.research_sources_v2 import FetchRequestV2
from efficiency_platform_agent.contracts.research_transport_v2 import (
    ResearchUrlSourcePolicyV2,
)
from efficiency_platform_agent.core.budget import RemainingBudget

from ._xml_safety import UnsafeXmlError, parse_safe_xml
from .live_connector import AsyncioPinnedHttpConnector, AsyncioTargetResolver
from .transport import (
    FetchLease,
    PinnedHttpConnector,
    SafeHttpTransport,
    TargetAuthorizer,
    TargetResolver,
)

type ProbeAdapterId = Literal[
    "rss_atom", "github_releases", "hacker_news", "arxiv", "gdelt"
]

_JSON_ADAPTERS = frozenset({"github_releases", "hacker_news", "gdelt"})
_XML_MEDIA_TYPES = frozenset(
    {"application/atom+xml", "application/rss+xml", "application/xml", "text/xml"}
)
_MAX_BODY_BYTES = 2 * 1024 * 1024


class LiveSourceProbeError(ValueError):
    """准入探针配置或调用不满足冻结边界。"""


@dataclass(frozen=True, slots=True)
class LiveSourceProbeTarget:
    """一次批准中冻结的来源、适配器、端点与授权摘要。"""

    source_id: str
    adapter_id: ProbeAdapterId
    endpoint_url: str
    authorization_scope_digest: str

    def __post_init__(self) -> None:
        try:
            split = urlsplit(self.endpoint_url)
            port = split.port or 443
        except ValueError as exc:
            raise LiveSourceProbeError("LIVE_PROBE_TARGET_INVALID") from exc
        if (
            not self.source_id.strip()
            or len(self.source_id) > 128
            or self.adapter_id
            not in {"rss_atom", "github_releases", "hacker_news", "arxiv", "gdelt"}
            or split.scheme != "https"
            or not split.hostname
            or split.username is not None
            or split.password is not None
            or split.fragment
            or port != 443
            or len(self.authorization_scope_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.authorization_scope_digest
            )
        ):
            raise LiveSourceProbeError("LIVE_PROBE_TARGET_INVALID")


class LiveSourceProbe:
    """通过 SafeHttpTransport 执行单端点读取并校验适配器顶层 Schema。"""

    def __init__(
        self,
        targets: tuple[LiveSourceProbeTarget, ...],
        *,
        connector: PinnedHttpConnector | None = None,
        resolver: TargetResolver | None = None,
        url_policy: TargetAuthorizer,
    ) -> None:
        if not targets or len(targets) > 8:
            raise LiveSourceProbeError("LIVE_PROBE_TARGET_COUNT_INVALID")
        by_url = {target.endpoint_url: target for target in targets}
        source_ids = {target.source_id for target in targets}
        if len(by_url) != len(targets) or len(source_ids) != len(targets):
            raise LiveSourceProbeError("LIVE_PROBE_TARGET_DUPLICATED")
        self._targets = by_url
        self._resolver = resolver or AsyncioTargetResolver()
        self._transport = SafeHttpTransport(
            connector or AsyncioPinnedHttpConnector(),
            url_policy=url_policy,
        )

    async def probe(self, endpoint_url: str) -> dict[str, object]:
        """只允许读取冻结端点；重定向仍逐跳受原 host 策略限制。"""

        target = self._targets.get(endpoint_url)
        if target is None:
            raise LiveSourceProbeError("LIVE_PROBE_TARGET_NOT_REGISTERED")
        host = urlsplit(target.endpoint_url).hostname
        if host is None:  # pragma: no cover - 已由 Target 构造校验
            raise LiveSourceProbeError("LIVE_PROBE_TARGET_INVALID")
        request_hash = hashlib.sha256(
            f"{target.source_id}\n{target.endpoint_url}".encode()
        ).hexdigest()[:24]
        content = await self._transport.fetch(
            FetchRequestV2(
                request_id=f"x04-probe-{request_hash}",
                source_id=target.source_id,
                tenant_id="x04-source-admission",
                run_id=f"x04-run-{request_hash}",
                lease_id=f"x04-lease-{request_hash}",
                authorization_scope_digest=target.authorization_scope_digest,
                candidate_id=f"x04-document-{request_hash}",
                url=target.endpoint_url,
            ),
            FetchLease(
                source_policy=ResearchUrlSourcePolicyV2(allowed_hosts=(host,)),
                resolver=self._resolver,
                remaining_budget=RemainingBudget(
                    iterations=0,
                    tool_calls=4,
                    input_tokens=0,
                    output_tokens=0,
                    cost_microunits=0,
                    timeout_ms=10_000,
                ),
                max_wire_bytes=_MAX_BODY_BYTES,
                max_decoded_bytes=_MAX_BODY_BYTES,
                max_redirects=3,
                connect_timeout_seconds=3.0,
                request_timeout_seconds=10.0,
            ),
        )
        return {
            "status_code": content.status_code,
            "schema_valid": _schema_valid(
                target.adapter_id,
                media_type=content.media_type,
                body=content.body,
            ),
        }


def _schema_valid(
    adapter_id: ProbeAdapterId, *, media_type: str, body: bytes
) -> bool:
    if not body or len(body) > _MAX_BODY_BYTES:
        return False
    if adapter_id in {"rss_atom", "arxiv"}:
        if media_type not in _XML_MEDIA_TYPES and not media_type.endswith("+xml"):
            return False
        try:
            root = parse_safe_xml(body)
        except UnsafeXmlError:
            return False
        local_name = _local_name(root.tag)
        if adapter_id == "arxiv":
            return root.tag == "{http://www.w3.org/2005/Atom}feed"
        if local_name == "feed":
            return True
        if local_name not in {"rss", "RDF"}:
            return False
        return any(_local_name(child.tag) == "channel" for child in root)
    if adapter_id not in _JSON_ADAPTERS or not (
        media_type == "application/json" or media_type.endswith("+json")
    ):
        return False
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if adapter_id == "github_releases":
        return isinstance(payload, list) and all(
            isinstance(item, dict)
            and isinstance(item.get("id"), int)
            and not isinstance(item.get("id"), bool)
            and isinstance(item.get("draft"), bool)
            and isinstance(item.get("prerelease"), bool)
            for item in payload
        )
    if adapter_id == "hacker_news":
        return isinstance(payload, list) and all(
            isinstance(item, int) and not isinstance(item, bool) and item > 0
            for item in payload
        )
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("articles"), list)
        and all(isinstance(item, dict) for item in payload["articles"])
    )


def _local_name(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


__all__ = ["LiveSourceProbe", "LiveSourceProbeError", "LiveSourceProbeTarget"]
