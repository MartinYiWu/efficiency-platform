"""请求排队后必须重查同任务停止信号，不能再向上游发送。"""

import asyncio

import httpx
import pytest
from test_paid_http_guard import ledger

from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.providers.paid_http import (
    PaidBudgetTransportError,
    PaidHttpTransport,
)


async def test_stopped_queued_request_never_reaches_upstream(tmp_path):
    calls = []
    slots = asyncio.Semaphore(0)
    control = RunControl()
    book = ledger(tmp_path)
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(
                lambda req: (calls.append(req), httpx.Response(200))[1]
            ),
            "deepseek",
            request_slots=slots,
        )
    ) as client:
        with execution_scope(control):
            waiting = asyncio.create_task(
                client.post(
                    "https://model.test/chat/completions",
                    json={"model": "test-model", "max_tokens": 10},
                )
            )
        await asyncio.sleep(0)
        control.stop()
        slots.release()
        with pytest.raises(PaidBudgetTransportError) as caught:
            await waiting
    assert caught.value.code == "AGENT_TASK_STOPPED"
    assert not calls and book.snapshot()["calls"] == 0
    assert slots._value == 1


async def test_task_close_also_cancels_direct_http_children(tmp_path):
    entered = asyncio.Event()
    control = RunControl()
    book = ledger(tmp_path)

    async def upstream(request):
        entered.set()
        await asyncio.Event().wait()

    async with httpx.AsyncClient(
        transport=PaidHttpTransport(book, httpx.MockTransport(upstream), "deepseek")
    ) as client:
        with execution_scope(control):
            waiting = asyncio.create_task(
                client.post(
                    "https://model.test/chat/completions",
                    json={"model": "test-model", "max_tokens": 10},
                )
            )
        await entered.wait()
        try:
            await control.close()
            assert waiting.done()
            assert book.snapshot()["inflight"] == 0
            assert book.snapshot()["cost_microunits"] == 10
        finally:
            waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)


async def test_task_close_closes_unread_response_after_request_task_has_finished(
    tmp_path,
):
    control = RunControl()
    book = ledger(tmp_path)
    slots = asyncio.Semaphore(1)
    closed = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"unread synthetic body"

        async def aclose(self):
            closed.append(True)

    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(lambda req: httpx.Response(200, stream=Stream())),
            "deepseek",
            request_slots=slots,
        )
    ) as client:
        with execution_scope(control):
            task = asyncio.create_task(
                client.send(
                    client.build_request(
                        "POST",
                        "https://model.test/chat/completions",
                        json={"model": "test-model", "max_tokens": 10},
                    ),
                    stream=True,
                )
            )
        response = await task
        try:
            assert book.snapshot()["inflight"] == 1
            await control.close()
            assert book.snapshot()["inflight"] == 0
            assert slots._value == 1
            assert closed == [True]
        finally:
            await response.aclose()
