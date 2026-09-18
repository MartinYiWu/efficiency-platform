"""真实安全连接器的纯内存 HTTP/1.1 契约测试。"""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass, field

import pytest

from efficiency_platform_agent.contracts.research_sources_v2 import FetchRequestV2
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.providers.research.live_connector import (
    AsyncioPinnedHttpConnector,
    AsyncioTargetResolver,
    PinnedConnectorError,
)
from efficiency_platform_agent.providers.research.transport import (
    FetchLease,
    SafeHttpTransport,
)
from efficiency_platform_agent.security.url_policy import (
    ResearchUrlSourcePolicy,
    UrlPolicy,
)

PUBLIC = "93.184.216.34"


class _SslObject:
    def selected_alpn_protocol(self) -> str:
        return "http/1.1"


@dataclass
class _Writer:
    written: bytearray = field(default_factory=bytearray)
    closed: bool = False

    def write(self, value: bytes) -> None:
        self.written.extend(value)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None

    def get_extra_info(self, name: str):
        return _SslObject() if name == "ssl_object" else None


def _reader(payload: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader(limit=70_000)
    reader.feed_data(payload)
    reader.feed_eof()
    return reader


def _target(url: str = "https://news.example.test/path?q=ai"):
    return UrlPolicy().authorize(
        url,
        ResearchUrlSourcePolicy(("news.example.test",)),
        (PUBLIC,),
    )


def _install_connection(monkeypatch, payload: bytes):
    captured: dict[str, object] = {}
    writer = _Writer()

    async def open_connection(host, port, **kwargs):
        captured.update({"host": host, "port": port, **kwargs})
        return _reader(payload), writer

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    return captured, writer


@pytest.mark.asyncio
async def test_connector_pins_ip_and_uses_original_host_for_tls_and_http(
    monkeypatch,
) -> None:
    captured, writer = _install_connection(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}",
    )

    response = await AsyncioPinnedHttpConnector().request(
        _target(),
        headers={"accept": "application/json"},
        connect_timeout=1.0,
        request_timeout=2.0,
        max_wire_bytes=1024,
    )

    assert captured["host"] == PUBLIC
    assert captured["port"] == 443
    assert captured["server_hostname"] == "news.example.test"
    assert captured["ssl"] is not None
    request = bytes(writer.written)
    assert request.startswith(b"GET /path?q=ai HTTP/1.1\r\n")
    assert b"Host: news.example.test\r\n" in request
    assert b"Connection: close\r\n" in request
    assert response.status_code == 200
    assert response.body_chunks == (b"{}",)
    assert writer.closed is True


@pytest.mark.asyncio
async def test_connector_decodes_chunked_framing_without_counting_frames(
    monkeypatch,
) -> None:
    _, writer = _install_connection(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
        b"Transfer-Encoding: chunked\r\n\r\n"
        b"5\r\nhello\r\n6\r\n world\r\n0\r\nX-Ignored: yes\r\n\r\n",
    )

    response = await AsyncioPinnedHttpConnector().request(
        _target(),
        headers={},
        connect_timeout=1.0,
        request_timeout=2.0,
        max_wire_bytes=11,
    )

    assert response.body_chunks == (b"hello", b" world")
    assert writer.closed is True


@pytest.mark.asyncio
async def test_connector_rejects_oversized_body_and_closes_socket(monkeypatch) -> None:
    _, writer = _install_connection(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 6\r\n\r\n123456",
    )

    with pytest.raises(PinnedConnectorError, match="CONNECTOR_BODY_TOO_LARGE"):
        await AsyncioPinnedHttpConnector().request(
            _target(),
            headers={},
            connect_timeout=1.0,
            request_timeout=2.0,
            max_wire_bytes=5,
        )

    assert writer.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Length: 1\r\n\r\na",
        b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\na",
        b"HTTP/1.1 200 OK\r\nBad Header: x\r\n\r\n",
        b"HTTP/1.1 200 OK\r\n Folded: x\r\n\r\n",
    ],
)
async def test_connector_rejects_ambiguous_or_malformed_response(
    monkeypatch, payload: bytes
) -> None:
    _install_connection(monkeypatch, payload)

    with pytest.raises(PinnedConnectorError, match="CONNECTOR_RESPONSE_INVALID"):
        await AsyncioPinnedHttpConnector().request(
            _target(),
            headers={},
            connect_timeout=1.0,
            request_timeout=2.0,
            max_wire_bytes=1024,
        )


@pytest.mark.asyncio
async def test_connector_rejects_forged_target_before_opening_socket(
    monkeypatch,
) -> None:
    calls = 0

    async def forbidden(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(asyncio, "open_connection", forbidden)
    valid = _target()
    forged = valid.__class__(
        url=valid.url,
        host=valid.host,
        port=valid.port,
        verified_ips=valid.verified_ips,
        connect_ip=valid.connect_ip,
        tls_server_name="evil.example",
        resolution_digest=valid.resolution_digest,
    )

    with pytest.raises(PinnedConnectorError, match="CONNECTOR_TARGET_INVALID"):
        await AsyncioPinnedHttpConnector().request(
            forged,
            headers={},
            connect_timeout=1.0,
            request_timeout=2.0,
            max_wire_bytes=1024,
        )

    assert calls == 0


@pytest.mark.asyncio
async def test_connector_rejects_request_header_injection_before_socket(
    monkeypatch,
) -> None:
    calls = 0

    async def forbidden(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(asyncio, "open_connection", forbidden)

    with pytest.raises(PinnedConnectorError, match="CONNECTOR_REQUEST_INVALID"):
        await AsyncioPinnedHttpConnector().request(
            _target(),
            headers={"accept": "text/plain\r\nX-Evil: yes"},
            connect_timeout=1.0,
            request_timeout=2.0,
            max_wire_bytes=1024,
        )

    assert calls == 0


@pytest.mark.asyncio
async def test_resolver_returns_deduplicated_addresses_for_policy_validation(
    monkeypatch,
) -> None:
    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        del host, port, family, type, proto, flags
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (PUBLIC, 443)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (PUBLIC, 443)),
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0),
            ),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    addresses = await AsyncioTargetResolver().resolve("news.example.test", 443)

    assert addresses == (PUBLIC, "2606:2800:220:1:248:1893:25c8:1946")


@pytest.mark.asyncio
async def test_connector_rejects_space_in_request_target_before_socket(
    monkeypatch,
) -> None:
    calls = 0

    async def forbidden(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(asyncio, "open_connection", forbidden)

    with pytest.raises(PinnedConnectorError, match="CONNECTOR_TARGET_INVALID"):
        await AsyncioPinnedHttpConnector().request(
            _target("https://news.example.test/bad path"),
            headers={},
            connect_timeout=1.0,
            request_timeout=2.0,
            max_wire_bytes=1024,
        )

    assert calls == 0


@pytest.mark.asyncio
async def test_connector_cannot_override_owned_request_headers(monkeypatch) -> None:
    calls = 0

    async def forbidden(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(asyncio, "open_connection", forbidden)

    with pytest.raises(PinnedConnectorError, match="CONNECTOR_REQUEST_INVALID"):
        await AsyncioPinnedHttpConnector().request(
            _target(),
            headers={"user-agent": "other"},
            connect_timeout=1.0,
            request_timeout=2.0,
            max_wire_bytes=1024,
        )

    assert calls == 0


@pytest.mark.asyncio
async def test_safe_transport_and_live_connector_integrate_without_real_network(
    monkeypatch,
) -> None:
    _install_connection(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 5\r\n\r\nhello",
    )

    class Resolver:
        async def resolve(self, host: str, port: int) -> tuple[str, ...]:
            assert (host, port) == ("news.example.test", 443)
            return (PUBLIC,)

    transport = SafeHttpTransport(AsyncioPinnedHttpConnector(), url_policy=UrlPolicy())
    request = FetchRequestV2(
        request_id="request-1",
        source_id="source-1",
        tenant_id="tenant-1",
        run_id="run-1",
        lease_id="lease-1",
        authorization_scope_digest="a" * 64,
        candidate_id="candidate-1",
        url="https://news.example.test/path",
    )
    lease = FetchLease(
        source_policy=ResearchUrlSourcePolicy(("news.example.test",)),
        resolver=Resolver(),
        remaining_budget=RemainingBudget(1, 1, 0, 0, 0, 5_000),
        max_wire_bytes=1024,
        max_decoded_bytes=1024,
    )

    fetched = await transport.fetch(request, lease)

    assert fetched.body == b"hello"
    assert fetched.final_url == "https://news.example.test/path"
    assert fetched.downloaded_bytes == 5
    assert fetched.request_count == 1


@pytest.mark.asyncio
async def test_connector_rejects_chunk_object_amplification(monkeypatch) -> None:
    body = b"1\r\nx\r\n" * 4097 + b"0\r\n\r\n"
    _install_connection(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" + body,
    )

    with pytest.raises(PinnedConnectorError, match="CONNECTOR_RESPONSE_INVALID"):
        await AsyncioPinnedHttpConnector().request(
            _target(),
            headers={},
            connect_timeout=1.0,
            request_timeout=2.0,
            max_wire_bytes=5000,
        )


@pytest.mark.asyncio
async def test_connector_rejects_unbounded_content_length_integer(monkeypatch) -> None:
    _install_connection(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\nContent-Length: " + b"9" * 5000 + b"\r\n\r\n",
    )

    with pytest.raises(PinnedConnectorError, match="CONNECTOR_RESPONSE_INVALID"):
        await AsyncioPinnedHttpConnector().request(
            _target(),
            headers={},
            connect_timeout=1.0,
            request_timeout=2.0,
            max_wire_bytes=5000,
        )


@pytest.mark.asyncio
async def test_connector_ignores_repeated_set_cookie_without_exposing_it(
    monkeypatch,
) -> None:
    _install_connection(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/atom+xml\r\n"
        b"Set-Cookie: first=secret\r\n"
        b"Set-Cookie: second=secret\r\n"
        b"Content-Length: 5\r\n\r\nhello",
    )

    response = await AsyncioPinnedHttpConnector().request(
        _target(),
        headers={},
        connect_timeout=1.0,
        request_timeout=2.0,
        max_wire_bytes=5000,
    )

    assert response.status_code == 200
    assert response.body_chunks == (b"hello",)
    assert "set-cookie" not in response.headers
