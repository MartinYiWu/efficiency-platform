"""压缩响应仅用合成数据做离线验收。"""

import gzip
import json
import zlib

import pytest

from efficiency_platform_agent.core.paid_budget import PaidUsage
from efficiency_platform_agent.providers.paid_usage import PaidUsageCollector


@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
@pytest.mark.parametrize("provider", ["deepseek", "embedding", "rerank"])
def test_compressed_json_usage(encoding: str, provider: str) -> None:
    payload = {
        "deepseek": {
            "choices": [{"finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        },
        "embedding": {"data": [], "usage": {"total_tokens": 12}},
        "rerank": {"output": {"results": []}, "usage": {"total_tokens": 12}},
    }[provider]
    body = json.dumps(payload).encode()
    wire = gzip.compress(body) if encoding == "gzip" else zlib.compress(body)
    collector = PaidUsageCollector(
        provider, "application/json", content_encoding=encoding
    )
    for byte in wire:
        collector.feed(bytes([byte]))
    assert collector.usage is None
    collector.end()
    assert collector.usage == PaidUsage(12, 4 if provider == "deepseek" else 0)


@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
def test_compressed_sse_split_bytes(encoding: str) -> None:
    body = (
        "data: "
        + json.dumps(
            {
                "choices": [{"delta": {"content": "中文"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            },
            ensure_ascii=False,
        )
        + "\r\n\r\ndata: [DONE]\n\n"
    ).encode()
    wire = gzip.compress(body) if encoding == "gzip" else zlib.compress(body)
    collector = PaidUsageCollector(
        "deepseek", "text/event-stream", content_encoding=encoding
    )
    for byte in wire:
        collector.feed(bytes([byte]))
    assert collector.usage is None
    collector.end()
    assert collector.usage == PaidUsage(12, 4)


@pytest.mark.parametrize(
    "damage", ["truncated", "checksum", "members", "trailing", "unknown", "expansion"]
)
@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
def test_unprovable_compression_cannot_refund(damage: str, encoding: str) -> None:
    body = b'{"data":[],"usage":{"total_tokens":12}}'
    wire = gzip.compress(body) if encoding == "gzip" else zlib.compress(body)
    if damage == "truncated":
        wire = wire[:-1]
    elif damage == "checksum":
        wire = wire[:-1] + bytes([wire[-1] ^ 1])
    elif damage == "members":
        wire += gzip.compress(b" ")
    elif damage == "trailing":
        wire += b"x"
    elif damage == "unknown":
        encoding = "br"
    elif damage == "expansion":
        expanded = body + b" " * 262144
        wire = (
            gzip.compress(expanded) if encoding == "gzip" else zlib.compress(expanded)
        )
    collector = PaidUsageCollector(
        "embedding", "application/json", content_encoding=encoding
    )
    for offset in range(0, len(wire), 3):
        collector.feed(wire[offset : offset + 3])
    collector.end()
    assert collector.usage is None
    assert len(collector.buffer) <= 262144


@pytest.mark.parametrize("encoding", ["", "identity", " GZip "])
def test_identity_and_normalized_encoding(encoding: str) -> None:
    body = b'{"data":[],"usage":{"total_tokens":12}}'
    collector = PaidUsageCollector(
        "embedding", "application/json", content_encoding=encoding
    )
    collector.feed(gzip.compress(body) if encoding.strip().lower() == "gzip" else body)
    collector.end()
    assert collector.usage == PaidUsage(12, 0)


def test_compressed_sse_cumulative_expansion_is_bounded() -> None:
    wire = gzip.compress(b": ignored\n" * 900000)
    collector = PaidUsageCollector(
        "deepseek", "text/event-stream", content_encoding="gzip"
    )
    for byte in wire:
        collector.feed(bytes([byte]))
    collector.end()
    assert collector.invalid
    assert collector.usage is None


@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
@pytest.mark.parametrize("whole", [False, True])
def test_compressed_sse_can_consume_more_than_one_buffer(
    encoding: str, whole: bool
) -> None:
    body = b": ignored\n" * 30000 + (
        b'data: {"choices":[{"finish_reason":"stop"}],'
        b'"usage":{"prompt_tokens":12,"completion_tokens":4}}\n\n'
        b"data: [DONE]\n\n"
    )
    wire = gzip.compress(body) if encoding == "gzip" else zlib.compress(body)
    collector = PaidUsageCollector(
        "deepseek", "text/event-stream", content_encoding=encoding
    )
    if whole:
        collector.feed(wire)
    else:
        for byte in wire:
            collector.feed(bytes([byte]))
    collector.end()
    assert collector.usage == PaidUsage(12, 4)
