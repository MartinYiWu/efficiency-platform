import asyncio

import pytest

from efficiency_platform_agent.orchestration.cancellation import (
    InMemoryCancellationSignal,
)


@pytest.mark.asyncio
async def test_request_wakes_waiter_and_is_idempotent() -> None:
    signal = InMemoryCancellationSignal()
    waiter = asyncio.create_task(signal.wait_requested("run-1"))
    await asyncio.sleep(0)
    await signal.request("run-1")
    assert await asyncio.wait_for(waiter, 0.2) is None
    assert await signal.is_requested("run-1") is True
    await signal.request("run-1")
