"""遗忘必须阻断已经复制的回放与已经排队的实时正文。"""
import asyncio

import pytest

from efficiency_platform_agent.api.sse import stream_run_events
from efficiency_platform_agent.runtime.event_hub import EventHub


async def erase(hub):
    scrub = getattr(hub, "scrub_memory_run", None)
    assert callable(scrub), "受信遗忘需要事件缓存物理擦除与持久执行门禁对应的进程墓碑"
    await scrub("run")


@pytest.mark.asyncio
async def test_open_replay_cannot_emit_its_copied_body_after_scrub():
    hub = EventHub()
    await hub.publish_next("run", "run_started", {})
    await hub.publish_next("run", "assistant_delta", {"text": "synthetic-forget-marker"})
    await hub.publish_next("run", "stream_done", {"status": "succeeded"})
    stream = stream_run_events(hub, "run")
    copied = await hub.replay("run", 0)
    assert "run_started" in await anext(stream)
    await erase(hub)
    assert copied == []
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert await hub.replay("run", 0) == []
    with pytest.raises(ValueError):
        await hub.publish_next("run", "assistant_delta", {"text": "late"})


@pytest.mark.asyncio
async def test_scrub_drains_existing_subscription_queue_and_wakes_waiter():
    hub = EventHub()
    queued, waiting = hub.subscribe("run"), hub.subscribe("run")
    await hub.publish_next("run", "assistant_delta", {"text": "synthetic-forget-marker"})
    await anext(waiting)
    wait_task = asyncio.create_task(anext(waiting))
    await asyncio.sleep(0)
    await erase(hub)
    with pytest.raises(StopAsyncIteration):
        await anext(queued)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(wait_task, 1)
    assert queued._queue.empty()
    assert waiting._queue.empty()
    assert hub.subscriber_count("run") == 0


@pytest.mark.asyncio
async def test_sse_checks_persistent_authority_before_each_copied_replay_event():
    hub = EventHub()
    allowed = True

    async def authority():
        return allowed

    await hub.publish_next("run", "run_started", {})
    await hub.publish_next("run", "assistant_delta", {"text": "synthetic-forget-marker"})
    stream = stream_run_events(hub, "run", can_emit=authority)
    await anext(stream)
    allowed = False
    with pytest.raises(StopAsyncIteration):
        await anext(stream)


@pytest.mark.asyncio
async def test_tombstones_never_evict_and_reopen_old_scrubbed_run():
    hub = EventHub()
    for index in range(1024):
        await hub.scrub_memory_run(f"closed-{index}")
    with pytest.raises(ValueError, match="MEMORY_EVENT_FENCE_CAPACITY"):
        await hub.scrub_memory_run("overflow")
    with pytest.raises(ValueError):
        await hub.publish_next("closed-0", "assistant_delta", {"text": "late"})
    assert len(hub._memory_scrubbed) == 1024
