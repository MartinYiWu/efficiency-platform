"""合成响应验证结算诊断与编码协商，不连接外部服务。"""

import asyncio
import gzip
import json
import logging
import time

import httpx
import pytest

from efficiency_platform_agent.core.paid_budget import PaidBudgetPlan, PaidPriceLimit
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.providers.paid_http import PaidHttpTransport
from efficiency_platform_agent.providers.paid_usage import PaidUsageCollector


def sse(usage=None):
    return (
        "data: "
        + json.dumps(
            {
                "choices": [
                    {"delta": {"content": "PRIVATE_ANSWER"}, "finish_reason": "stop"}
                ],
                "usage": usage
                if usage is not None
                else {"prompt_tokens": 10, "completion_tokens": 2},
                "PRIVATE_FIELD": "PRIVATE_RESPONSE",
            }
        )
        + "\n\ndata: [DONE]\n\n"
    ).encode()


@pytest.fixture
def book(tmp_path):
    result = SqlitePaidBudgetLedger(tmp_path / "diagnostics-fake.sqlite3")
    result.authorize(
        PaidBudgetPlan(
            "fake-diagnostics",
            10,
            1000,
            int(time.time() * 1000) + 60000,
            10,
            1000,
            60000,
            1,
            3,
            100000,
            100000,
            100000,
            100000,
            100000,
            100000,
        ),
        (
            PaidPriceLimit(
                "deepseek",
                "fake-model",
                10000,
                10,
                100,
                "离线合成费率",
                "fake-v1",
                10000,
                1,
                0,
                1,
            ),
        ),
    )
    return result


@pytest.mark.parametrize(
    "case,expected",
    [
        ("valid", "VALID_USAGE"),
        ("missing_reasoning", "MISSING_REASONING_USAGE"),
        ("bad_usage", "INVALID_USAGE"),
        ("bad_usage_and_missing_reasoning", "INVALID_USAGE"),
        ("conflict", "CONFLICTING_USAGE"),
        ("missing_done", "MISSING_DONE"),
        ("missing_terminal", "MISSING_TERMINAL"),
        ("missing_usage", "MISSING_USAGE"),
        ("trailing", "INCOMPLETE_SSE"),
        ("invalid_event", "INVALID_EVENT"),
        ("unsupported", "UNSUPPORTED_ENCODING"),
        ("compressed_truncation", "INCOMPLETE_COMPRESSION"),
        ("compressed_damage", "INVALID_COMPRESSION"),
        ("oversize", "RESPONSE_LIMIT_EXCEEDED"),
    ],
)
def test_collector_reports_fixed_reason_without_response_content(case, expected):
    wire = sse()
    encoding = ""
    if case in {"bad_usage", "bad_usage_and_missing_reasoning"}:
        wire = sse({"prompt_tokens": True, "completion_tokens": 2})
    elif case == "conflict":
        wire = wire.replace(
            b"data: [DONE]",
            b'data: {"usage":{"prompt_tokens":11,"completion_tokens":2}}\n\ndata: [DONE]',
        )
    elif case == "missing_done":
        wire = wire.replace(b"data: [DONE]\n\n", b"")
    elif case == "missing_terminal":
        wire = wire.replace(b'"finish_reason": "stop"', b'"finish_reason": null')
    elif case == "missing_usage":
        wire = b'data: {"choices":[{"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    elif case == "trailing":
        wire += b"data: PRIVATE_TRUNCATED"
    elif case == "invalid_event":
        wire = b"data: PRIVATE_MALFORMED\n\n"
    elif case == "unsupported":
        encoding = "PRIVATE_HEADER"
    elif case.startswith("compressed_"):
        encoding = "gzip"
        wire = gzip.compress(wire)
        wire = wire[:-1] if case.endswith("truncation") else b"damaged gzip"
    elif case == "oversize":
        wire = b"x" * 262145
    collector = PaidUsageCollector(
        "deepseek",
        "text/event-stream",
        thinking=case in {"missing_reasoning", "bad_usage_and_missing_reasoning"},
        content_encoding=encoding,
    )
    collector.feed(wire)
    collector.end()
    diagnostic = collector.diagnostics()
    assert diagnostic["reason"] == expected
    assert (collector.usage is not None) == (case == "valid")
    assert set(diagnostic) == {
        "reason",
        "encoding",
        "sse",
        "done",
        "terminal",
        "invalid",
        "usage_seen",
        "reasoning_usage_seen",
    }
    assert "PRIVATE" not in json.dumps(diagnostic)


@pytest.mark.parametrize("encoding", [None, "identity", "gzip", "deflate, zstd"])
async def test_transport_only_offers_encodings_provable_by_collector(book, encoding):
    sent = []

    async def send(request):
        sent.append(request.headers["Accept-Encoding"])
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse()
        )

    async with httpx.AsyncClient(
        transport=PaidHttpTransport(book, httpx.MockTransport(send), "deepseek"),
    ) as client:
        await client.post(
            "https://offline.invalid/chat/completions",
            headers={"Accept-Encoding": encoding} if encoding is not None else {},
            json={
                "model": "fake-model",
                "max_tokens": 10,
                "thinking": {"type": "disabled"},
            },
        )
    assert sent == ["gzip, deflate"]
    assert book.details()["attempts"][0]["state"] == "settled"


@pytest.mark.parametrize(
    "mode",
    [
        "settled",
        "missing_reasoning",
        "early_close",
        "close_error",
        "cancel",
        "read_error",
    ],
)
async def test_transport_logs_once_with_no_sensitive_fields(book, caplog, mode):
    caplog.set_level(logging.INFO, logger="efficiency_platform_agent.execution")
    slots = asyncio.Semaphore(1)
    waiting_for_eof = asyncio.Event()

    class Wire(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield sse()
            if mode == "cancel":
                waiting_for_eof.set()
                await asyncio.Event().wait()
            elif mode == "read_error":
                raise httpx.ReadError("PRIVATE_READ_ERROR")

        async def aclose(self):
            if mode == "close_error":
                raise httpx.ReadError("PRIVATE_CLOSE_ERROR")

    async def send(request):
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=Wire()
        )

    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book, httpx.MockTransport(send), "deepseek", request_slots=slots
        ),
    ) as client:
        request = client.build_request(
            "POST",
            "https://offline.invalid/chat/completions",
            headers={"Authorization": "Bearer PRIVATE_CREDENTIAL"},
            json={
                "model": "fake-model",
                "messages": [{"role": "user", "content": "PRIVATE_PROMPT"}],
                "max_tokens": 10,
                "thinking": {
                    "type": "enabled" if mode == "missing_reasoning" else "disabled"
                },
            },
        )
        response = await client.send(request, stream=True)
        if mode == "early_close":
            iterator = response.aiter_raw()
            await anext(iterator)
            await response.aclose()
            await iterator.aclose()
        elif mode == "cancel":
            task = asyncio.create_task(response.aread())
            await waiting_for_eof.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif mode in {"close_error", "read_error"}:
            with pytest.raises(httpx.ReadError):
                await response.aread()
        else:
            await response.aread()
        await response.aclose()
    attempt = book.details()["attempts"][0]
    assert attempt["state"] == ("settled" if mode == "settled" else "unknown")
    assert book.snapshot()["inflight"] == 0
    assert slots._value == 1
    logs = [
        r.getMessage()
        for r in caplog.records
        if "event=paid_http_usage" in r.getMessage()
    ]
    assert len(logs) == 1
    log = logs[0]
    assert attempt["reservation_id"] in log
    assert f"outcome={'settled' if mode == 'settled' else 'unknown'}" in log
    assert "PRIVATE" not in log
    assert {
        "settled": "VALID_USAGE",
        "missing_reasoning": "MISSING_REASONING_USAGE",
        "early_close": "AWAITING_EOF",
        "close_error": "VALID_USAGE",
        "cancel": "AWAITING_EOF",
        "read_error": "AWAITING_EOF",
    }[mode] in log
    assert f"complete={mode not in {'early_close', 'cancel', 'read_error'}}" in log
    assert f"close_ok={mode != 'close_error'}" in log


async def test_diagnostic_handler_failure_does_not_change_response_or_slot(book):
    logger = logging.getLogger("efficiency_platform_agent.execution")

    class BrokenHandler(logging.Handler):
        def emit(self, record):
            raise RuntimeError("PRIVATE_DIAGNOSTIC_ERROR")

    slots = asyncio.Semaphore(1)
    handler = BrokenHandler()
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        async with httpx.AsyncClient(
            transport=PaidHttpTransport(
                book,
                httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        headers={"content-type": "text/event-stream"},
                        content=sse(),
                    )
                ),
                "deepseek",
                request_slots=slots,
            ),
        ) as client:
            response = await client.post(
                "https://offline.invalid/chat/completions",
                json={
                    "model": "fake-model",
                    "max_tokens": 10,
                    "thinking": {"type": "disabled"},
                },
            )
        assert response.status_code == 200
        assert response.content == sse()
        assert book.details()["attempts"][0]["state"] == "settled"
        assert book.snapshot()["inflight"] == 0
        assert slots._value == 1
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate"])
async def test_generation_provider_settles_fragmented_full_usage(book, encoding):
    import zlib

    from efficiency_platform_agent.core.run import (
        JsonObject,
        ProviderMessage,
        ProviderRequest,
    )
    from efficiency_platform_agent.providers.deepseek_stream import (
        DeepSeekStreamingProvider,
    )

    wire = sse(
        {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
            "prompt_cache_hit_tokens": 4,
            "prompt_cache_miss_tokens": 6,
            "completion_tokens_details": {"reasoning_tokens": 1},
        }
    )
    if encoding == "gzip":
        wire = gzip.compress(wire)
    elif encoding == "deflate":
        wire = zlib.compress(wire)

    class Wire(httpx.AsyncByteStream):
        async def __aiter__(self):
            for offset in range(0, len(wire), 3):
                yield wire[offset : offset + 3]

    async def send(request):
        assert request.url.host == "offline.invalid"
        return httpx.Response(
            200,
            headers={
                "content-type": "text/event-stream",
                "content-encoding": encoding,
            },
            stream=Wire(),
        )

    async with httpx.AsyncClient(
        transport=PaidHttpTransport(book, httpx.MockTransport(send), "deepseek"),
    ) as client:
        provider = DeepSeekStreamingProvider(
            client,
            "fake-model",
            api_key="synthetic",
            base_url="https://offline.invalid",
            max_retries=0,
        )
        result = await provider.complete(
            ProviderRequest(
                "test",
                (ProviderMessage("user", "synthetic"),),
                JsonObject((("max_tokens", 10),)),
                5000,
            )
        )
        assert result.error is None
        assert result.usage.input_tokens == 10
        assert result.usage.output_tokens == 2
    attempt = book.details()["attempts"][0]
    assert attempt["state"] == "settled"
    assert attempt["reported_usage"] == {
        "input_tokens": 10,
        "output_tokens": 2,
        "cached_tokens": 4,
        "reasoning_tokens": 1,
    }
    assert book.snapshot()["calls"] == 1
    assert book.snapshot()["inflight"] == 0
