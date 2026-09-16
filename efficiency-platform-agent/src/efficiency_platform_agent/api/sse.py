"""将版本化运行事件编码为支持重连与保活的 SSE 响应。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable

from fastapi.sse import ServerSentEvent

from efficiency_platform_agent.contracts.events import RunEventV1
from efficiency_platform_agent.contracts.stream_events import RunStreamEventV1
from efficiency_platform_agent.runtime.event_hub import EventHub


def parse_last_event_id(value: str | None) -> int:
    """解析 Last-Event-ID，仅允许正整数游标。"""
    if value is None:
        return 0
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("INVALID_EVENT_CURSOR")
    return int(value)


def encode_events(events: Iterable[RunEventV1]) -> Iterable[ServerSentEvent]:
    """把事件契约映射为 SSE 的 id、event 和 JSON data。"""
    for event in events:
        yield ServerSentEvent(
            id=str(event.sequence),
            event=event.event_type,
            raw_data=event.model_dump_json(),
        )


def render_events(events: Iterable[RunEventV1]) -> Iterable[str]:
    """把 ServerSentEvent 转成 StreamingResponse 可发送的文本块。"""
    for item in encode_events(events):
        lines: list[str] = []
        if item.id is not None:
            lines.append(f"id: {item.id}")
        if item.event is not None:
            lines.append(f"event: {item.event}")
        if item.raw_data is not None:
            lines.extend(f"data: {line}" for line in item.raw_data.splitlines() or [""])
        lines.append("")
        yield "\n".join(lines) + "\n"


def render_sse(event: RunStreamEventV1) -> str:
    """将一个流事件渲染为标准 SSE 文本块。"""
    return (
        f"id: {event.sequence}\n"
        f"event: {event.event}\n"
        f"data: {event.model_dump_json()}\n\n"
    )


async def stream_run_events(
    event_hub: EventHub,
    run_id: str,
    *,
    after_sequence: int = 0,
    keep_alive_seconds: float = 15.0,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[str]:
    """先回放再监听实时事件，并在空闲期发送 SSE 注释保活。"""
    if keep_alive_seconds <= 0:
        raise ValueError("keep_alive_seconds 必须大于零")
    subscription = event_hub.subscribe(run_id)
    cursor = after_sequence
    try:
        replayed = await event_hub.replay(run_id, after_sequence)
        for event in replayed:
            if event.sequence <= cursor:
                continue
            cursor = event.sequence
            yield render_sse(event)
            if event.event == "stream_done":
                return
        if event_hub.is_closed(run_id):
            return
        while True:
            if is_disconnected is not None and await is_disconnected():
                return
            try:
                event = await asyncio.wait_for(
                    anext(subscription), timeout=keep_alive_seconds
                )
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if event.sequence <= cursor:
                continue
            cursor = event.sequence
            yield render_sse(event)
            if event.event == "stream_done":
                return
    finally:
        await subscription.aclose()


__all__ = [
    "encode_events",
    "parse_last_event_id",
    "render_events",
    "render_sse",
    "stream_run_events",
]
