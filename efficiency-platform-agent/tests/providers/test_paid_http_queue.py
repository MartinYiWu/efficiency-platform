"""验证单并发排队；全部使用临时Fake账本与MockTransport。"""

import asyncio
import gzip
import json
import time

import httpx
import pytest

from efficiency_platform_agent.core.paid_budget import (
    PaidBudgetPlan,
    PaidPriceLimit,
    paid_scope,
)
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.providers.paid_http import (
    PaidHttpTransport,
    paid_error_code,
)


def make_ledger(tmp_path):
    result = SqlitePaidBudgetLedger(tmp_path / "queue-fake.sqlite3")
    result.authorize(
        PaidBudgetPlan(
            "fake-queue",
            10,
            1000,
            int(time.time() * 1000) + 60_000,
            10,
            1000,
            60_000,
            1,
            3,
            100000,
            100000,
            100000,
            100000,
            100000,
            100000,
        ),
        tuple(
            PaidPriceLimit(
                provider,
                model,
                10000,
                0,
                100,
                "离线合成费率",
                "fake-v1",
                10000,
                1,
                1,
                0,
            )
            for provider, model in [
                ("embedding", "mock-embedding"),
                ("rerank", "mock-rerank"),
            ]
        ),
    )
    return result


async def test_two_providers_share_one_slot_until_response_body_closes(tmp_path):
    ledger = make_ledger(tmp_path)
    slots = asyncio.Semaphore(1)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    class HeldStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            entered.set()
            await release.wait()
            yield b'{"data":[],"usage":{"prompt_tokens":10,"total_tokens":10}}'

    async def send(request):
        calls.append(request.url.path)
        if request.url.path == "/embedding":
            return httpx.Response(
                200, headers={"Content-Type": "application/json"}, stream=HeldStream()
            )
        return httpx.Response(
            200, json={"output": {"results": []}, "usage": {"input_tokens": 10}}
        )

    async with (
        httpx.AsyncClient(
            transport=PaidHttpTransport(
                ledger, httpx.MockTransport(send), "embedding", request_slots=slots
            )
        ) as embedding,
        httpx.AsyncClient(
            transport=PaidHttpTransport(
                ledger, httpx.MockTransport(send), "rerank", request_slots=slots
            )
        ) as rerank,
    ):
        with paid_scope("one-case"):
            first = asyncio.create_task(
                embedding.post(
                    "https://offline.invalid/embedding",
                    json={"model": "mock-embedding", "input": ["a"]},
                )
            )
            await entered.wait()
            second = asyncio.create_task(
                rerank.post(
                    "https://offline.invalid/rerank",
                    json={
                        "model": "mock-rerank",
                        "input": {"query": "a", "documents": ["b"]},
                    },
                )
            )
            await asyncio.sleep(0)
            assert calls == ["/embedding"]
            assert ledger.snapshot()["calls"] == 1
            assert not second.done()
            release.set()
            responses = await asyncio.wait_for(asyncio.gather(first, second), 2)
            assert [response.status_code for response in responses] == [200, 200]
    assert calls == ["/embedding", "/rerank"]
    assert ledger.snapshot()["calls"] == 2
    assert ledger.snapshot()["inflight"] == 0
    assert slots._value == 1


async def test_cancelled_waiter_and_guard_rejection_release_only_owned_slot(tmp_path):
    ledger = make_ledger(tmp_path)
    slots = asyncio.Semaphore(1)
    await slots.acquire()
    dispatched = []

    async def send(request):
        dispatched.append(request)
        return httpx.Response(
            200, json={"data": [], "usage": {"prompt_tokens": 1, "total_tokens": 1}}
        )

    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            ledger, httpx.MockTransport(send), "embedding", request_slots=slots
        )
    ) as client:
        waiting = asyncio.create_task(
            client.post(
                "https://offline.invalid/embedding",
                json={"model": "mock-embedding", "input": ["a"]},
            )
        )
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        assert ledger.snapshot()["calls"] == 0
        assert slots.locked()
        slots.release()
        ledger.stop("fake-queue", "offline_stop")
        with pytest.raises(httpx.RequestError) as error:
            await client.post(
                "https://offline.invalid/embedding",
                json={"model": "mock-embedding", "input": ["a"]},
            )
        assert paid_error_code(error.value) is not None
        assert slots._value == 1
        assert not dispatched


async def test_wire_compressed_usage_settles_without_changing_sdk_body(tmp_path):
    ledger = make_ledger(tmp_path)
    slots = asyncio.Semaphore(1)
    payload = {"data": [], "usage": {"prompt_tokens": 10, "total_tokens": 10}}

    async def send(request):
        assert request.url.host == "offline.invalid"
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json", "Content-Encoding": "gzip"},
            content=gzip.compress(json.dumps(payload).encode()),
        )

    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            ledger, httpx.MockTransport(send), "embedding", request_slots=slots
        )
    ) as client:
        with paid_scope("compressed-question"):
            response = await client.post(
                "https://offline.invalid/embedding",
                json={"model": "mock-embedding", "input": ["a"]},
            )
            assert response.json() == payload
    attempt = ledger.details()["attempts"][0]
    assert attempt["state"] == "settled"
    assert attempt["reported_usage"]["input_tokens"] == 10
    assert slots._value == 1
