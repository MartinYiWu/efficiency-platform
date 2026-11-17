"""付费保护通过本地传输测试，绝不访问外部服务。"""

import asyncio
import time

import httpx
import pytest

from efficiency_platform_agent.core.paid_budget import (
    PaidBudgetPlan,
    PaidPriceLimit,
    paid_scope,
)
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.providers.paid_http import PaidHttpTransport


def ledger(tmp_path, calls=3, max_429=2, duration=10000):
    result = SqlitePaidBudgetLedger(tmp_path / "budget.sqlite3")
    result.authorize(
        PaidBudgetPlan(
            "test",
            calls,
            100,
            int(time.time() * 1000) + 10000,
            calls,
            100,
            duration,
            2,
            max_429,
            1000000,
            1000000,
            1000000,
            1000000,
            1000000,
            1000000,
        ),
        (
            PaidPriceLimit(
                "deepseek",
                "test-model",
                10000,
                100,
                10,
                "synthetic test upper bound",
                "test-v1",
                20000,
                1,
                0,
                1,
            ),
        ),
    )
    return result


async def test_no_authorization_sends_zero_requests(tmp_path):
    sent = []
    inner = httpx.MockTransport(
        lambda request: (sent.append(request), httpx.Response(200))[1]
    )
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            SqlitePaidBudgetLedger(tmp_path / "b.db"), inner, "deepseek"
        )
    ) as client:
        with pytest.raises(httpx.RequestError):
            await client.post(
                "https://model.test/chat/completions",
                json={"model": "test-model", "max_tokens": 10},
            )
    assert not sent


async def test_each_attempt_consumes_budget_and_survives_new_transport(tmp_path):
    book = ledger(tmp_path, calls=2)
    sent = []
    for index in range(3):
        inner = httpx.MockTransport(
            lambda request: (sent.append(request), httpx.Response(200, text="ok"))[1]
        )
        async with httpx.AsyncClient(
            transport=PaidHttpTransport(book, inner, "deepseek")
        ) as client:
            with paid_scope("same-question"):
                if index < 2:
                    assert (
                        await client.post(
                            "https://model.test/chat/completions",
                            json={"model": "test-model", "max_tokens": 10},
                        )
                    ).status_code == 200
                else:
                    with pytest.raises(httpx.RequestError):
                        await client.post(
                            "https://model.test/chat/completions",
                            json={"model": "test-model", "max_tokens": 10},
                        )
    assert len(sent) == 2


@pytest.mark.parametrize("status,allowed", [(402, 1), (429, 2)])
async def test_payment_and_rate_limit_open_shared_persistent_circuit(
    tmp_path, status, allowed
):
    book = ledger(tmp_path)
    sent = []
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(lambda r: (sent.append(r), httpx.Response(status))[1]),
            "deepseek",
        )
    ) as client:
        for _ in range(allowed):
            await client.post(
                "https://model.test/chat/completions",
                json={"model": "test-model", "max_tokens": 10},
            )
        with pytest.raises(httpx.RequestError):
            await client.post(
                "https://model.test/chat/completions",
                json={"model": "test-model", "max_tokens": 10},
            )
    assert len(sent) == allowed


async def test_stream_time_limit_closes_body_and_does_not_refund(tmp_path):
    book = ledger(tmp_path, duration=30)
    closed = []

    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(0.2)
            yield b"late"

        async def aclose(self):
            closed.append(True)

    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(lambda r: httpx.Response(200, stream=Slow())),
            "deepseek",
        )
    ) as client:
        with pytest.raises(httpx.RequestError):
            await client.post(
                "https://model.test/chat/completions",
                json={"model": "test-model", "max_tokens": 10},
            )
    assert closed


async def test_unknown_model_or_missing_maximum_never_dispatches(tmp_path):
    book = ledger(tmp_path)
    sent = []
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(lambda r: (sent.append(r), httpx.Response(200))[1]),
            "deepseek",
        )
    ) as client:
        for payload in [{"model": "other", "max_tokens": 10}, {"model": "test-model"}]:
            with pytest.raises(httpx.RequestError):
                await client.post("https://model.test/chat/completions", json=payload)
    assert not sent


async def test_real_provider_internal_retry_and_schema_retry_share_attempt_budget(
    tmp_path,
):
    from efficiency_platform_agent.core.run import (
        JsonObject,
        ProviderMessage,
        ProviderRequest,
    )
    from efficiency_platform_agent.providers.deepseek_stream import (
        DeepSeekStreamingProvider,
    )

    book = ledger(tmp_path, calls=1)
    sent = []
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(lambda r: (sent.append(r), httpx.Response(429))[1]),
            "deepseek",
        )
    ) as client:
        provider = DeepSeekStreamingProvider(
            client,
            "test-model",
            api_key="synthetic",
            base_url="https://model.test",
            max_retries=1,
        )
        result = await provider.complete(
            ProviderRequest(
                "test",
                (ProviderMessage("user", "test"),),
                JsonObject((("max_tokens", 10),)),
                1000,
            )
        )
    assert len(sent) == 1
    assert result.error is not None and result.error.category == "budget"
    assert book.snapshot()["calls"] == 1


async def test_cancel_keeps_charge_and_releases_only_concurrency(tmp_path):
    book = ledger(tmp_path)
    arrived = asyncio.Event()

    class Never(httpx.AsyncByteStream):
        async def __aiter__(self):
            arrived.set()
            await asyncio.Event().wait()
            yield b""

        async def aclose(self):
            pass

    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(lambda r: httpx.Response(200, stream=Never())),
            "deepseek",
        )
    ) as client:
        task = asyncio.create_task(
            client.post(
                "https://model.test/chat/completions",
                json={"model": "test-model", "max_tokens": 10},
            )
        )
        await arrived.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert book.snapshot()["calls"] == 1
    assert book.snapshot()["cost_microunits"] == 10
    assert book.snapshot()["inflight"] == 0


async def test_embedding_and_rerank_share_global_budget_with_generation(tmp_path):
    book = SqlitePaidBudgetLedger(tmp_path / "all.db")
    book.authorize(
        PaidBudgetPlan(
            "all",
            2,
            100,
            int(time.time() * 1000) + 10000,
            2,
            100,
            1000,
            2,
            2,
            100000,
            1000,
            1000,
            100000,
            1000,
            1000,
        ),
        tuple(
            PaidPriceLimit(p, "m", 10000, 100, 10, "test", "v1", 20000, 1, 0, 1)
            for p in ["deepseek", "embedding", "rerank"]
        ),
    )
    sent = []
    for provider in ["deepseek", "embedding", "rerank"]:
        async with httpx.AsyncClient(
            transport=PaidHttpTransport(
                book,
                httpx.MockTransport(lambda r: (sent.append(r), httpx.Response(200))[1]),
                provider,
            )
        ) as client:
            payload = {
                "model": "m",
                **({"max_tokens": 10} if provider == "deepseek" else {}),
            }
            if provider == "rerank":
                with pytest.raises(httpx.RequestError):
                    await client.post("https://model.test/request", json=payload)
            else:
                await client.post("https://model.test/request", json=payload)
    assert len(sent) == 2


async def test_amount_reservation_blocks_before_network_even_with_unknown_usage(
    tmp_path,
):
    book = SqlitePaidBudgetLedger(tmp_path / "money.db")
    book.authorize(
        PaidBudgetPlan(
            "money",
            100,
            15,
            int(time.time() * 1000) + 10000,
            100,
            15,
            1000,
            2,
            2,
            100000,
            1000,
            1000,
            100000,
            1000,
            1000,
        ),
        (PaidPriceLimit("deepseek", "m", 1000, 100, 10, "test", "v1", 10000, 1, 0, 1),),
    )
    sent = []
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(lambda r: (sent.append(r), httpx.Response(500))[1]),
            "deepseek",
        )
    ) as client:
        await client.post(
            "https://model.test/request", json={"model": "m", "max_tokens": 1}
        )
        with pytest.raises(httpx.RequestError):
            await client.post(
                "https://model.test/request", json={"model": "m", "max_tokens": 1}
            )
    assert len(sent) == 1 and book.snapshot()["cost_microunits"] == 10


async def test_loopback_http_is_limited_before_second_real_socket_request(tmp_path):
    received = []

    async def handle(reader, writer):
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            length = int(
                next(
                    line.split(b":", 1)[1]
                    for line in headers.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                )
            )
            await reader.readexactly(length)
            received.append(True)
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    book = ledger(tmp_path, calls=1)
    try:
        async with httpx.AsyncClient(
            transport=PaidHttpTransport(
                book, httpx.AsyncHTTPTransport(retries=0), "deepseek"
            ),
            trust_env=False,
        ) as client:
            await client.post(
                f"http://127.0.0.1:{port}/chat/completions",
                json={"model": "test-model", "max_tokens": 10},
            )
            with pytest.raises(httpx.RequestError):
                await client.post(
                    f"http://127.0.0.1:{port}/chat/completions",
                    json={"model": "test-model", "max_tokens": 10},
                )
        assert received == [True]
    finally:
        server.close()
        await server.wait_closed()


async def test_provider_drains_done_before_usage_settlement(tmp_path):
    from efficiency_platform_agent.core.run import (
        JsonObject,
        ProviderMessage,
        ProviderRequest,
    )
    from efficiency_platform_agent.providers.deepseek_stream import (
        DeepSeekStreamingProvider,
    )

    book = ledger(tmp_path)
    body = 'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":2}}\n\ndata: [DONE]\n\n'
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(
                lambda r: httpx.Response(
                    200, text=body, headers={"content-type": "text/event-stream"}
                )
            ),
            "deepseek",
        )
    ) as client:
        p = DeepSeekStreamingProvider(
            client, "test-model", api_key="synthetic", base_url="https://model.test"
        )
        result = await p.complete(
            ProviderRequest(
                "test",
                (ProviderMessage("user", "synthetic"),),
                JsonObject(
                    (
                        ("max_tokens", 10),
                        ("thinking", JsonObject((("type", "disabled"),))),
                    )
                ),
                1000,
            )
        )
        assert result.error is None
    assert book.details()["attempts"][0]["state"] == "settled"
    assert book.snapshot()["accounting"]["actual_tokens"]["input_tokens"] == 10


async def test_sse_usage_settles_cost_and_reuses_only_confirmed_unused_tokens(tmp_path):
    # 合成价格：100输入(40缓存)+30输出=100+60-20=140微元；推理20已在输出30内。
    # 创建独立临时计划以避免复用真实授权。
    second = SqlitePaidBudgetLedger(tmp_path / "settle.db")
    plan = PaidBudgetPlan(
        "settle",
        3,
        100000,
        int(time.time() * 1000) + 10000,
        3,
        100000,
        10000,
        2,
        2,
        100000,
        100,
        100,
        100000,
        100,
        100,
    )
    price = PaidPriceLimit(
        "deepseek",
        "m",
        10000,
        100,
        30000,
        "synthetic",
        "v1",
        20000,
        1000000,
        500000,
        2000000,
    )
    second.authorize(plan, (price,))
    raw = 'data: {"choices":[{"finish_reason":"stop"}],"usage":{"prompt_tokens":100,"completion_tokens":30,"prompt_cache_hit_tokens":40,"completion_tokens_details":{"reasoning_tokens":20}}}\n\ndata: [DONE]\n\n'
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            second,
            httpx.MockTransport(
                lambda r: httpx.Response(
                    200, text=raw, headers={"content-type": "text/event-stream"}
                )
            ),
            "deepseek",
        )
    ) as client:
        with paid_scope("q"):
            await client.post(
                "https://model.test/chat/completions",
                json={"model": "m", "max_tokens": 60},
            )
    s = second.snapshot()
    assert s["cost_microunits"] == 140
    assert s["accounting"]["actual_tokens"] == {
        "input_tokens": 100,
        "output_tokens": 30,
        "reasoning_tokens": 20,
    }
    assert s["accounting"]["held_cost_microunits"] == 0
    assert second.details()["attempts"][0]["pricing_version"] == "v1"


async def test_missing_or_cancelled_stream_usage_keeps_full_reservation(tmp_path):
    book = ledger(tmp_path)
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(
                lambda r: httpx.Response(
                    200,
                    text='data: {"choices":[{"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
                    headers={"content-type": "text/event-stream"},
                )
            ),
            "deepseek",
        )
    ) as client:
        await client.post(
            "https://model.test/chat/completions",
            json={"model": "test-model", "max_tokens": 10},
        )
    assert book.details()["attempts"][0]["state"] == "unknown"
    assert book.snapshot()["cost_microunits"] == 10
    assert book.snapshot()["accounting"]["effective_tokens"]["output_tokens"] == 10


async def test_question_token_limit_blocks_second_attempt_before_dispatch(tmp_path):
    book = SqlitePaidBudgetLedger(tmp_path / "token-limit.db")
    p = PaidBudgetPlan(
        "tokens",
        100,
        10000,
        int(time.time() * 1000) + 10000,
        100,
        10000,
        10000,
        2,
        2,
        100000,
        15,
        15,
        100000,
        15,
        15,
    )
    book.authorize(
        p,
        (
            PaidPriceLimit(
                "deepseek", "m", 10000, 100, 10, "test", "v1", 20000, 1, 0, 1
            ),
        ),
    )
    sent = []
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(lambda r: (sent.append(True), httpx.Response(500))[1]),
            "deepseek",
        )
    ) as client:
        with paid_scope("q"):
            await client.post(
                "https://model.test/chat/completions",
                json={"model": "m", "max_tokens": 10},
            )
            with pytest.raises(httpx.RequestError):
                await client.post(
                    "https://model.test/chat/completions",
                    json={"model": "m", "max_tokens": 10},
                )
    assert len(sent) == 1


async def test_reported_usage_over_bound_stops_budget_without_underreporting(tmp_path):
    book = ledger(tmp_path)
    raw = {
        "choices": [{"finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": 30000,
            "completion_tokens": 2,
            "completion_tokens_details": {"reasoning_tokens": 0},
        },
    }
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(lambda r: httpx.Response(200, json=raw)),
            "deepseek",
        )
    ) as client:
        with pytest.raises(httpx.RequestError):
            await client.post(
                "https://model.test/chat/completions",
                json={"model": "test-model", "max_tokens": 10},
            )
    assert book.snapshot()["stopped"] == "usage_exceeded"
    assert book.details()["attempts"][0]["reported_usage"]["input_tokens"] == 30000


async def test_incomplete_stream_with_usage_or_close_failure_never_refunds(tmp_path):
    book = ledger(tmp_path)
    prefix = b'data: {"choices":[{"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":2}}\n\n'

    class Broken(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield prefix
            raise httpx.ReadError("synthetic connection lost")

        async def aclose(self):
            pass

    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(
                lambda r: httpx.Response(
                    200, stream=Broken(), headers={"content-type": "text/event-stream"}
                )
            ),
            "deepseek",
        )
    ) as client:
        with pytest.raises(httpx.RequestError):
            await client.post(
                "https://model.test/chat/completions",
                json={
                    "model": "test-model",
                    "max_tokens": 10,
                    "thinking": {"type": "disabled"},
                },
            )
    assert book.details()["attempts"][0]["state"] == "unknown"
    assert book.snapshot()["cost_microunits"] == 10


async def test_embedding_json_usage_settles_input_without_output_or_reasoning(tmp_path):
    book = SqlitePaidBudgetLedger(tmp_path / "embedding.db")
    p = PaidBudgetPlan(
        "e",
        2,
        100000,
        int(time.time() * 1000) + 10000,
        2,
        100000,
        10000,
        1,
        2,
        100000,
        0,
        0,
        100000,
        0,
        0,
    )
    book.authorize(
        p,
        (
            PaidPriceLimit(
                "embedding", "e", 10000, 0, 20000, "test", "v1", 20000, 1000000, 0, 0
            ),
        ),
    )
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(
                lambda r: httpx.Response(
                    200,
                    json={
                        "data": [],
                        "usage": {"prompt_tokens": 12, "total_tokens": 12},
                    },
                )
            ),
            "embedding",
        )
    ) as client:
        await client.post(
            "https://model.test/embeddings", json={"model": "e", "input": ["synthetic"]}
        )
    assert book.snapshot()["cost_microunits"] == 12
    assert book.details()["attempts"][0]["reported_usage"] == {
        "input_tokens": 12,
        "output_tokens": 0,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
    }
