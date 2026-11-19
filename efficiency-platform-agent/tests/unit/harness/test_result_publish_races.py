"""结果栅栏已进入后的await边界必须复核，权限拒绝不能进入正文fallback。"""

import asyncio

import pytest

from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.core.run import JsonObject
from efficiency_platform_agent.runtime.event_hub import EventHub
from tests.unit.harness.test_memory_run_binding import request, service


async def test_stream_authority_failure_stops_remaining_body_and_full_fallback():
    from efficiency_platform_agent.core.context_dispatch import (
        ResultPublishDenied,
        bind_result_publish_guard,
    )

    runtime = service()
    record, _ = await runtime._create_queued(request())
    record = record.transition(RunStatus.RUNNING).transition(
        RunStatus.SUCCEEDED, output=JsonObject((("content", "full-result"),))
    )

    class Guard:
        blocked = False

        async def check(self, run_id):
            assert run_id == record.run_id
            if self.blocked:
                raise ResultPublishDenied("MEMORY_RESULT_PUBLISH_DENIED")

    guard = Guard()

    async def chunks(*args):
        yield "first-legitimate"
        guard.blocked = True
        raise RuntimeError("synthetic presenter failure")

    runtime.output_streamer = chunks
    with bind_result_publish_guard(guard), pytest.raises(ResultPublishDenied):
        await runtime._publish_result_events(record)
    events = await runtime.event_hub.replay(record.run_id, 0)
    assert [e.payload["delta"] for e in events if e.event == "assistant_delta"] == [
        "first-legitimate"
    ]
    assert runtime.event_hub.is_memory_publication_blocked(record.run_id)


async def test_hub_rechecks_after_waiting_for_lock_before_buffer_and_queue():
    from efficiency_platform_agent.core.context_dispatch import (
        ResultPublishDenied,
        bind_result_publish_guard,
    )

    hub = EventHub()
    entered = asyncio.Event()

    class Guard:
        blocked = False

        async def check(self, run_id):
            entered.set()
            if self.blocked:
                raise ResultPublishDenied("MEMORY_RESULT_PUBLISH_DENIED")

    guard = Guard()
    await hub._lock.acquire()
    with bind_result_publish_guard(guard):
        task = asyncio.create_task(
            hub.publish_next("run", "assistant_delta", {"delta": "late-body"})
        )
    try:
        await asyncio.wait_for(entered.wait(), 1)
        guard.blocked = True
    finally:
        hub._lock.release()
    with pytest.raises(ResultPublishDenied):
        await task
    assert not await hub.replay("run", 0)
    assert hub.is_memory_publication_blocked("run")


async def test_ordinary_presenter_failure_still_has_legacy_fallback():
    runtime = service()
    record, _ = await runtime._create_queued(request())
    record = record.transition(RunStatus.RUNNING).transition(
        RunStatus.SUCCEEDED, output=JsonObject((("content", "legacy-full-result"),))
    )

    async def chunks(*args):
        raise RuntimeError("synthetic legacy presenter failure")
        yield

    runtime.output_streamer = chunks
    assert await runtime._publish_result_events(record)
    events = await runtime.event_hub.replay(record.run_id, 0)
    assert [e.payload["delta"] for e in events if e.event == "assistant_delta"] == [
        "legacy-full-result"
    ]
