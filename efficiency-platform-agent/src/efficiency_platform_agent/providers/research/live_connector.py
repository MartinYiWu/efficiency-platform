"""基于 asyncio 的 HTTPS IP 固定连接器。

该模块只实现单跳 HTTP/1.1 GET。URL/DNS/重定向授权仍由 ``SafeHttpTransport``
负责；连接器只连接授权对象中的 IP，并以原始 host 执行 TLS SNI 和证书校验。
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import math
import re
import socket
import ssl
from collections.abc import Mapping
from urllib.parse import urlsplit

from efficiency_platform_agent.contracts.research_transport_v2 import (
    AuthorizedTargetV2,
)

from .transport import PinnedResponse

_HEADER_LIMIT = 64 * 1024
_HEADER_LINE_LIMIT = 8 * 1024
_TRAILER_LIMIT = 16 * 1024
_READ_CHUNK_SIZE = 64 * 1024
_MAX_BODY_CHUNKS = 4096
_CHUNK_FRAMING_LIMIT = 64 * 1024
_TOKEN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
_STATUS = re.compile(rb"HTTP/1\.1 ([1-5][0-9]{2})(?: [\x20-\x7e]*)?\Z")
_FORBIDDEN_REQUEST_HEADERS = frozenset(
    {
        "connection",
        "content-length",
        "host",
        "accept-encoding",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "user-agent",
    }
)


class PinnedConnectorError(RuntimeError):
    """只携带稳定错误码，不保存远端响应正文。"""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class AsyncioPinnedHttpConnector:
    """禁代理、固定 IP、校验 SNI/证书的最小 HTTPS 连接器。"""

    supports_ip_pinning = True
    supports_tls_server_name = True
    verifies_certificates = True
    uses_environment_proxy = False

    def __init__(self) -> None:
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_alpn_protocols(["http/1.1"])
        self._ssl_context = context

    async def request(
        self,
        target: AuthorizedTargetV2,
        *,
        headers: Mapping[str, str],
        connect_timeout: float,
        request_timeout: float,
        max_wire_bytes: int,
    ) -> PinnedResponse:
        request = _request_bytes(target, headers)
        if (
            not math.isfinite(connect_timeout)
            or not math.isfinite(request_timeout)
            or connect_timeout <= 0
            or request_timeout <= 0
            or connect_timeout > request_timeout
            or isinstance(max_wire_bytes, bool)
            or max_wire_bytes <= 0
        ):
            raise PinnedConnectorError("CONNECTOR_REQUEST_INVALID")

        writer: asyncio.StreamWriter | None = None
        try:
            async with asyncio.timeout(request_timeout):
                reader, opened_writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        host=target.connect_ip,
                        port=target.port,
                        ssl=self._ssl_context,
                        server_hostname=target.tls_server_name,
                        limit=_HEADER_LIMIT + 1,
                    ),
                    timeout=connect_timeout,
                )
                writer = opened_writer
                _verify_tls(opened_writer)
                opened_writer.write(request)
                await opened_writer.drain()
                return await _read_response(reader, max_wire_bytes)
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            raise PinnedConnectorError("CONNECTOR_TIMEOUT") from exc
        except PinnedConnectorError:
            raise
        except (OSError, ssl.SSLError, asyncio.IncompleteReadError) as exc:
            raise PinnedConnectorError("CONNECTOR_IO_FAILED") from exc
        finally:
            if writer is not None:
                try:
                    writer.close()
                    await writer.wait_closed()
                except (OSError, ssl.SSLError):
                    pass


class AsyncioTargetResolver:
    """使用事件循环 DNS 解析；地址安全性由随后 UrlPolicy 全量校验。"""

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        if (
            not isinstance(host, str)
            or not host
            or isinstance(port, bool)
            or port != 443
        ):
            raise PinnedConnectorError("CONNECTOR_RESOLUTION_INVALID")
        try:
            answers = await asyncio.get_running_loop().getaddrinfo(
                host,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
        except (OSError, UnicodeError) as exc:
            raise PinnedConnectorError("CONNECTOR_RESOLUTION_FAILED") from exc
        addresses: list[str] = []
        for family, socktype, proto, _canonical, sockaddr in answers:
            if (
                family not in {socket.AF_INET, socket.AF_INET6}
                or socktype != socket.SOCK_STREAM
                or proto not in {0, socket.IPPROTO_TCP}
                or not isinstance(sockaddr, tuple)
                or not sockaddr
                or not isinstance(sockaddr[0], str)
            ):
                continue
            try:
                address = ipaddress.ip_address(sockaddr[0]).compressed
            except ValueError:
                continue
            if address not in addresses:
                addresses.append(address)
        if not addresses:
            raise PinnedConnectorError("CONNECTOR_RESOLUTION_FAILED")
        return tuple(addresses)


def _request_bytes(target: AuthorizedTargetV2, headers: Mapping[str, str]) -> bytes:
    _validate_target(target)
    try:
        split = urlsplit(target.url)
        request_target = split.path or "/"
        if split.query:
            request_target += f"?{split.query}"
        request_target_bytes = request_target.encode("ascii")
    except (UnicodeEncodeError, ValueError) as exc:
        raise PinnedConnectorError("CONNECTOR_TARGET_INVALID") from exc

    if any(byte <= 32 or byte == 127 for byte in request_target_bytes):
        raise PinnedConnectorError("CONNECTOR_TARGET_INVALID")

    normalized: list[tuple[str, str]] = []
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise PinnedConnectorError("CONNECTOR_REQUEST_INVALID")
        try:
            name_bytes = name.encode("ascii")
            value_bytes = value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise PinnedConnectorError("CONNECTOR_REQUEST_INVALID") from exc
        lowered = name.lower()
        if (
            not _TOKEN.fullmatch(name_bytes)
            or lowered in _FORBIDDEN_REQUEST_HEADERS
            or any(byte < 32 or byte == 127 for byte in value_bytes)
        ):
            raise PinnedConnectorError("CONNECTOR_REQUEST_INVALID")
        normalized.append((lowered, value))
    if len({name for name, _ in normalized}) != len(normalized):
        raise PinnedConnectorError("CONNECTOR_REQUEST_INVALID")

    lines = [
        b"GET " + request_target_bytes + b" HTTP/1.1",
        f"Host: {target.host}".encode("ascii"),
        b"Connection: close",
        b"Accept-Encoding: gzip, deflate",
        b"User-Agent: efficiency-platform-agent-research/2",
    ]
    lines.extend(
        f"{name}: {value}".encode("ascii") for name, value in sorted(normalized)
    )
    return b"\r\n".join(lines) + b"\r\n\r\n"


def _validate_target(target: AuthorizedTargetV2) -> None:
    if not isinstance(target, AuthorizedTargetV2):
        raise PinnedConnectorError("CONNECTOR_TARGET_INVALID")
    try:
        split = urlsplit(target.url)
        port = split.port or 443
        verified = tuple(
            ipaddress.ip_address(value).compressed for value in target.verified_ips
        )
        connect_ip = ipaddress.ip_address(target.connect_ip).compressed
    except (TypeError, ValueError) as exc:
        raise PinnedConnectorError("CONNECTOR_TARGET_INVALID") from exc
    if (
        split.scheme != "https"
        or split.hostname != target.host
        or split.username is not None
        or split.password is not None
        or split.fragment
        or target.port != port
        or target.port != 443
        or target.tls_server_name != target.host
        or not verified
        or verified != target.verified_ips
        or connect_ip != target.connect_ip
        or connect_ip not in verified
        or any(not _public_address(ipaddress.ip_address(value)) for value in verified)
    ):
        raise PinnedConnectorError("CONNECTOR_TARGET_INVALID")
    expected_digest = hashlib.sha256(
        "\n".join((target.host, str(target.port), *verified)).encode("ascii")
    ).hexdigest()
    if target.resolution_digest != expected_digest:
        raise PinnedConnectorError("CONNECTOR_TARGET_INVALID")


def _public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        address.is_global
        and not address.is_multicast
        and not address.is_unspecified
        and not address.is_reserved
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_private
        and not (
            isinstance(address, ipaddress.IPv6Address)
            and address.ipv4_mapped is not None
        )
    )


def _verify_tls(writer: asyncio.StreamWriter) -> None:
    tls = writer.get_extra_info("ssl_object")
    if tls is None:
        raise PinnedConnectorError("CONNECTOR_TLS_INVALID")
    selected = tls.selected_alpn_protocol()
    if selected not in {None, "http/1.1"}:
        raise PinnedConnectorError("CONNECTOR_TLS_INVALID")


async def _read_response(
    reader: asyncio.StreamReader, max_wire_bytes: int
) -> PinnedResponse:
    try:
        raw_headers = await reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
        raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID") from exc
    if len(raw_headers) > _HEADER_LIMIT:
        raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
    lines = raw_headers[:-4].split(b"\r\n")
    if not lines or not _STATUS.fullmatch(lines[0]):
        raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
    status_code = int(lines[0].split(b" ", 2)[1])
    headers = _parse_response_headers(lines[1:])
    transfer_encoding = headers.get("transfer-encoding")
    content_length = headers.get("content-length")
    if transfer_encoding is not None and content_length is not None:
        raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
    if 100 <= status_code < 200:
        raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
    if status_code in {204, 304}:
        chunks: tuple[bytes, ...] = ()
    elif transfer_encoding is not None:
        if transfer_encoding.lower() != "chunked":
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
        chunks = await _read_chunked(reader, max_wire_bytes)
    elif content_length is not None:
        if not content_length.isascii() or not content_length.isdigit():
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
        if len(content_length) > 20:
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
        try:
            length = int(content_length)
        except ValueError as exc:
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID") from exc
        if length > max_wire_bytes:
            raise PinnedConnectorError("CONNECTOR_BODY_TOO_LARGE")
        chunks = await _read_exact_body(reader, length)
    else:
        chunks = await _read_to_eof(reader, max_wire_bytes)
    return PinnedResponse(status_code, headers, chunks)


def _parse_response_headers(lines: list[bytes]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in lines:
        if not line or len(line) > _HEADER_LINE_LIMIT or line[:1] in {b" ", b"\t"}:
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
        name, separator, value = line.partition(b":")
        if not separator or not _TOKEN.fullmatch(name):
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
        lowered = name.decode("ascii").lower()
        stripped = value.strip(b" \t")
        if any(byte < 32 or byte == 127 for byte in stripped):
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
        # Cookie 与研究响应语义无关，且服务端合法地重复发送 Set-Cookie。
        # 直接丢弃可避免暴露凭据，也不放宽 framing header 的重复门禁。
        if lowered == "set-cookie":
            continue
        if lowered in parsed:
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
        try:
            parsed[lowered] = stripped.decode("ascii")
        except UnicodeDecodeError as exc:
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID") from exc
    return parsed


async def _read_exact_body(
    reader: asyncio.StreamReader, length: int
) -> tuple[bytes, ...]:
    if length == 0:
        return ()
    try:
        body = await reader.readexactly(length)
    except asyncio.IncompleteReadError as exc:
        raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID") from exc
    return (body,)


async def _read_to_eof(
    reader: asyncio.StreamReader, max_wire_bytes: int
) -> tuple[bytes, ...]:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await reader.read(min(_READ_CHUNK_SIZE, max_wire_bytes - size + 1))
        if not chunk:
            return tuple(chunks)
        size += len(chunk)
        if size > max_wire_bytes:
            raise PinnedConnectorError("CONNECTOR_BODY_TOO_LARGE")
        chunks.append(chunk)


async def _read_chunked(
    reader: asyncio.StreamReader, max_wire_bytes: int
) -> tuple[bytes, ...]:
    chunks: list[bytes] = []
    size = 0
    framing_size = 0
    while True:
        line = await _read_line(reader, _HEADER_LINE_LIMIT)
        size_token = line.split(b";", 1)[0]
        framing_size += len(line) + 2
        if (
            framing_size > _CHUNK_FRAMING_LIMIT
            or not size_token
            or len(size_token) > 16
            or not re.fullmatch(rb"[0-9A-Fa-f]+", size_token)
        ):
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
        chunk_size = int(size_token, 16)
        if chunk_size == 0:
            await _read_trailers(reader)
            return tuple(chunks)
        if size + chunk_size > max_wire_bytes:
            raise PinnedConnectorError("CONNECTOR_BODY_TOO_LARGE")
        if len(chunks) >= _MAX_BODY_CHUNKS:
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
        try:
            chunk = await reader.readexactly(chunk_size)
            ending = await reader.readexactly(2)
        except asyncio.IncompleteReadError as exc:
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID") from exc
        if ending != b"\r\n":
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
        framing_size += 2
        if framing_size > _CHUNK_FRAMING_LIMIT:
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
        chunks.append(chunk)
        size += chunk_size


async def _read_line(reader: asyncio.StreamReader, limit: int) -> bytes:
    try:
        line = await reader.readuntil(b"\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
        raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID") from exc
    if len(line) > limit or not line.endswith(b"\r\n"):
        raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
    return line[:-2]


async def _read_trailers(reader: asyncio.StreamReader) -> None:
    size = 0
    lines: list[bytes] = []
    while True:
        line = await _read_line(reader, _HEADER_LINE_LIMIT)
        size += len(line) + 2
        if size > _TRAILER_LIMIT:
            raise PinnedConnectorError("CONNECTOR_RESPONSE_INVALID")
        if not line:
            _parse_response_headers(lines)
            return
        lines.append(line)


__all__ = [
    "AsyncioPinnedHttpConnector",
    "AsyncioTargetResolver",
    "PinnedConnectorError",
]
