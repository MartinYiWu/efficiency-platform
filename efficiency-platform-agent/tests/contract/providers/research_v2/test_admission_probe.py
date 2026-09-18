"""X04 来源准入探针的离线契约测试。"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from efficiency_platform_agent.contracts.research_transport_v2 import (
    AuthorizedTargetV2,
)
from efficiency_platform_agent.providers.research.admission_probe import (
    LiveSourceProbe,
    LiveSourceProbeError,
    LiveSourceProbeTarget,
)
from efficiency_platform_agent.providers.research.transport import PinnedResponse
from efficiency_platform_agent.security.url_policy import UrlPolicy


class _StaticResolver:
    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        assert host == "feed.example"
        assert port == 443
        return ("93.184.216.34",)


class _PinnedConnector:
    supports_ip_pinning = True
    supports_tls_server_name = True
    verifies_certificates = True
    uses_environment_proxy = False

    def __init__(self, response: PinnedResponse) -> None:
        self.response = response
        self.targets: list[AuthorizedTargetV2] = []

    async def request(
        self,
        target: AuthorizedTargetV2,
        *,
        headers: Mapping[str, str],
        connect_timeout: float,
        request_timeout: float,
        max_wire_bytes: int,
    ) -> PinnedResponse:
        assert headers["accept"]
        assert 0 < connect_timeout <= request_timeout
        assert max_wire_bytes == 2 * 1024 * 1024
        self.targets.append(target)
        return self.response


def _target(adapter_id: str = "rss_atom") -> LiveSourceProbeTarget:
    return LiveSourceProbeTarget(
        source_id="source-free",
        adapter_id=adapter_id,
        endpoint_url="https://feed.example/rss",
        authorization_scope_digest="a" * 64,
    )


@pytest.mark.asyncio
async def test_live_probe_uses_pinned_transport_and_validates_feed_schema() -> None:
    connector = _PinnedConnector(
        PinnedResponse(
            status_code=200,
            headers={"content-type": "application/rss+xml"},
            body_chunks=(
                (
                    b'<?xml version="1.0"?><rss version="2.0"><channel>'
                    b"<title>AI</title></channel></rss>"
                ),
            ),
        )
    )
    probe = LiveSourceProbe(
        (_target(),),
        connector=connector,
        resolver=_StaticResolver(),
        url_policy=UrlPolicy(),
    )

    result = await probe.probe("https://feed.example/rss")

    assert result == {"status_code": 200, "schema_valid": True}
    assert connector.targets[0].connect_ip == "93.184.216.34"
    assert connector.targets[0].tls_server_name == "feed.example"


@pytest.mark.asyncio
async def test_live_probe_reports_schema_failure_without_accepting_json_shape() -> None:
    connector = _PinnedConnector(
        PinnedResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body_chunks=(b'{"unexpected": true}',),
        )
    )
    probe = LiveSourceProbe(
        (_target("hacker_news"),),
        connector=connector,
        resolver=_StaticResolver(),
        url_policy=UrlPolicy(),
    )

    result = await probe.probe("https://feed.example/rss")

    assert result == {"status_code": 200, "schema_valid": False}


@pytest.mark.asyncio
async def test_live_probe_rejects_endpoint_outside_frozen_target_set() -> None:
    probe = LiveSourceProbe(
        (_target(),),
        connector=_PinnedConnector(
            PinnedResponse(200, {"content-type": "application/rss+xml"}, ())
        ),
        resolver=_StaticResolver(),
        url_policy=UrlPolicy(),
    )

    with pytest.raises(LiveSourceProbeError, match="LIVE_PROBE_TARGET_NOT_REGISTERED"):
        await probe.probe("https://other.example/rss")
