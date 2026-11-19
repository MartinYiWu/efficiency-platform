"""面向本地联调的进程内流事件总线。"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Mapping
from typing import Any
from weakref import WeakValueDictionary

from efficiency_platform_agent.contracts.stream_events import (
    RunStreamEventV1,
    StreamEventName,
)
from efficiency_platform_agent.core.context_dispatch import (
    ResultPublishDenied,
    current_result_publish_guard,
    result_publish_guard_required,
)

_RESULT_BODY_EVENTS = frozenset({"assistant_delta", "deliverable"})

_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "connection_string",
        "dsn",
        "exception",
        "hidden_reasoning",
        "model_candidates",
        "password",
        "prompt",
        "rendered_prompt",
        "secret",
        "stack",
        "stacktrace",
        "token",
        "tool_args",
        "traceback",
        "raw_page",
    }
)
_SENSITIVE_TEXT = re.compile(
    r"(?:\bBearer\s+\S+|\bsk-[A-Za-z0-9_-]+|Traceback\s*\(|"
    r"(?:postgres(?:ql)?|redis|mysql|mongodb(?:\+srv)?)://)",
    re.IGNORECASE,
)
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_PASCAL_CASE_BOUNDARY = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")


def _validate_run_id(run_id: str) -> None:
    """拒绝空白 Run 标识。"""
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id 不能为空")


def _canonicalize_payload_key(key: object) -> str:
    """将常见键名形式统一为 snake_case，供结构化敏感键匹配。"""
    normalized = str(key).strip().replace("-", "_")
    normalized = _PASCAL_CASE_BOUNDARY.sub("_", normalized)
    normalized = _CAMEL_CASE_BOUNDARY.sub("_", normalized)
    return normalized.lower()


def _contains_sensitive_payload(value: Any) -> bool:
    """只按键名和稳定格式识别敏感信息，不读取环境变量。"""
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _canonicalize_payload_key(key)
            if normalized in _SENSITIVE_KEYS or _contains_sensitive_payload(child):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_sensitive_payload(child) for child in value)
    return isinstance(value, str) and _SENSITIVE_TEXT.search(value) is not None


def _snapshot(event: RunStreamEventV1) -> RunStreamEventV1:
    """复制事件及其可变 JSON 容器，隔离历史和各订阅者。"""
    return RunStreamEventV1.model_validate(event.model_dump(mode="python"))


def _closes_run(event: RunStreamEventV1) -> bool:
    """等待补充输入只结束当前 SSE 段，不封死可恢复的 Run。"""
    return (
        event.event == "stream_done" and event.payload.get("status") != "waiting_input"
    )


class _ReplayBatch(list[RunStreamEventV1]):
    pass


class EventSubscription(AsyncIterator[RunStreamEventV1]):
    """一个可显式关闭的 Run 实时订阅。"""

    def __init__(self, hub: EventHub, run_id: str) -> None:
        self._hub = hub
        self.run_id = run_id
        self._queue: asyncio.Queue[RunStreamEventV1 | None] = asyncio.Queue()
        self._closed = False
        self._current: RunStreamEventV1 | None = None

    def __aiter__(self) -> EventSubscription:
        return self

    async def __anext__(self) -> RunStreamEventV1:
        if self._closed:
            while not self._queue.empty():
                self._queue.get_nowait()
            raise StopAsyncIteration
        event = await self._queue.get()
        if self._closed or event is None or self._hub.is_memory_scrubbed(self.run_id):
            raise StopAsyncIteration
        if (
            self._hub.is_memory_publication_blocked(self.run_id)
            and event.event in _RESULT_BODY_EVENTS
        ):
            raise StopAsyncIteration
        self._current = event
        return event

    async def aclose(self) -> None:
        """幂等关闭订阅并释放 Hub 中的引用。"""
        if self._closed:
            return
        self._closed = True
        while not self._queue.empty():
            queued = self._queue.get_nowait()
            if queued is not None:
                queued.payload.clear()
        self._queue.put_nowait(None)
        self._hub._unsubscribe(self)


class EventHub:
    """提供历史回放、实时扇出和流终止记录的进程内事件 Hub。"""

    def __init__(self) -> None:
        self._history: dict[str, list[RunStreamEventV1]] = {}
        self._subscribers: dict[str, set[EventSubscription]] = {}
        self._closed_runs: set[str] = set()
        self._memory_scrubbed: set[str] = set()
        self._replays: WeakValueDictionary[int, _ReplayBatch] = WeakValueDictionary()
        self._lock = asyncio.Lock()
        self._blocked_memory_publication: set[str] = set()

    def block_memory_publication(self, run_id: str) -> None:
        _validate_run_id(run_id)
        self._blocked_memory_publication.add(run_id)

    def is_memory_publication_blocked(self, run_id: str) -> bool:
        return run_id in self._blocked_memory_publication

    async def _check_result_event(self, run_id: str, event: str) -> None:
        if event not in _RESULT_BODY_EVENTS:
            return
        guard = current_result_publish_guard()
        if (
            self.is_memory_publication_blocked(run_id)
            or guard is None
            and result_publish_guard_required()
        ):
            self.block_memory_publication(run_id)
            raise ResultPublishDenied("MEMORY_RESULT_PUBLISH_DENIED")
        if guard is not None:
            try:
                await guard.check(run_id)
            except ResultPublishDenied:
                self.block_memory_publication(run_id)
                raise

    async def publish(self, event: RunStreamEventV1) -> None:
        """按 Run 单调追加事件，并同步发送给当前订阅者。"""
        if not isinstance(event, RunStreamEventV1):
            raise TypeError("event 必须是 RunStreamEventV1")
        if _contains_sensitive_payload(event.payload):
            raise ValueError("事件 payload 包含禁止的敏感信息")
        await self._check_result_event(event.run_id, event.event)
        async with self._lock:
            await self._check_result_event(event.run_id, event.event)
            if event.run_id in self._closed_runs:
                raise ValueError("Run 事件流已经结束")
            history = self._history.setdefault(event.run_id, [])
            if history and event.sequence <= history[-1].sequence:
                raise ValueError("事件 sequence 必须递增")
            stored = _snapshot(event)
            history.append(stored)
            subscribers = tuple(self._subscribers.get(event.run_id, ()))
            if _closes_run(event):
                self._closed_runs.add(event.run_id)
            for subscription in subscribers:
                subscription._queue.put_nowait(_snapshot(stored))

    async def publish_next(
        self,
        run_id: str,
        event: StreamEventName,
        payload: Mapping[str, Any] | None = None,
    ) -> RunStreamEventV1:
        """在 Hub 锁内分配下一序号并发布，供多事件来源安全汇流。"""
        _validate_run_id(run_id)
        candidate = RunStreamEventV1(
            event=event,
            run_id=run_id,
            sequence=1,
            payload=dict(payload or {}),
        )
        if _contains_sensitive_payload(candidate.payload):
            raise ValueError("事件 payload 包含禁止的敏感信息")
        await self._check_result_event(run_id, event)
        async with self._lock:
            await self._check_result_event(run_id, event)
            if run_id in self._closed_runs:
                raise ValueError("Run 事件流已经结束")
            history = self._history.setdefault(run_id, [])
            stored = candidate.model_copy(
                update={"sequence": history[-1].sequence + 1 if history else 1}
            )
            stored = _snapshot(stored)
            history.append(stored)
            subscribers = tuple(self._subscribers.get(run_id, ()))
            if _closes_run(stored):
                self._closed_runs.add(run_id)
            for subscription in subscribers:
                subscription._queue.put_nowait(_snapshot(stored))
            return _snapshot(stored)

    async def replay(self, run_id: str, after_sequence: int) -> list[RunStreamEventV1]:
        """返回严格晚于游标的事件快照。"""
        _validate_run_id(run_id)
        if (
            not isinstance(after_sequence, int)
            or isinstance(after_sequence, bool)
            or after_sequence < 0
        ):
            raise ValueError("after_sequence 必须是非负整数")
        async with self._lock:
            if run_id in self._memory_scrubbed:
                return []
            replayed = _ReplayBatch(
                _snapshot(event)
                for event in self._history.get(run_id, ())
                if event.sequence > after_sequence
            )
            self._replays[id(replayed)] = replayed
            return replayed

    def subscribe(self, run_id: str) -> EventSubscription:
        """立即登记订阅，避免回放与实时监听之间丢失事件。"""
        _validate_run_id(run_id)
        subscription = EventSubscription(self, run_id)
        if run_id in self._memory_scrubbed:
            subscription._closed = True
            return subscription
        self._subscribers.setdefault(run_id, set()).add(subscription)
        return subscription

    def subscriber_count(self, run_id: str) -> int:
        """返回当前订阅数，供资源释放验证使用。"""
        return len(self._subscribers.get(run_id, ()))

    def is_closed(self, run_id: str) -> bool:
        """返回该 Run 是否已经发布 stream_done。"""
        return run_id in self._closed_runs

    def is_memory_scrubbed(self, run_id: str) -> bool:
        return run_id in self._memory_scrubbed

    async def scrub_memory_run(self, run_id: str) -> None:
        _validate_run_id(run_id)
        async with self._lock:
            if (
                run_id not in self._memory_scrubbed
                and len(self._memory_scrubbed) >= 1024
            ):
                raise ValueError("MEMORY_EVENT_FENCE_CAPACITY")
            self._memory_scrubbed.add(run_id)
            self._closed_runs.add(run_id)
            history = self._history.pop(run_id, None)
            if history is not None:
                for event in history:
                    event.payload.clear()
                history.clear()
            for subscription in tuple(self._subscribers.get(run_id, ())):
                if subscription._current is not None:
                    subscription._current.payload.clear()
                await subscription.aclose()
            for replayed in tuple(self._replays.values()):
                if replayed and replayed[0].run_id == run_id:
                    for event in replayed:
                        event.payload.clear()
                    replayed.clear()

    def _unsubscribe(self, subscription: EventSubscription) -> None:
        subscribers = self._subscribers.get(subscription.run_id)
        if subscribers is None:
            return
        subscribers.discard(subscription)
        if not subscribers:
            self._subscribers.pop(subscription.run_id, None)


__all__ = ["EventHub", "EventSubscription"]
