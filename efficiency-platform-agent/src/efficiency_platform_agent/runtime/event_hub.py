"""面向本地联调的进程内流事件总线。"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Mapping
from typing import Any

from efficiency_platform_agent.contracts.stream_events import (
    RunStreamEventV1,
    StreamEventName,
)

_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "connection_string",
        "dsn",
        "exception",
        "password",
        "prompt",
        "rendered_prompt",
        "secret",
        "stack",
        "stacktrace",
        "token",
        "traceback",
    }
)
_SENSITIVE_TEXT = re.compile(
    r"(?:\bBearer\s+\S+|\bsk-[A-Za-z0-9_-]+|Traceback\s*\(|"
    r"(?:postgres(?:ql)?|redis|mysql|mongodb(?:\+srv)?)://)",
    re.IGNORECASE,
)


def _validate_run_id(run_id: str) -> None:
    """拒绝空白 Run 标识。"""
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id 不能为空")


def _contains_sensitive_payload(value: Any) -> bool:
    """只按键名和稳定格式识别敏感信息，不读取环境变量。"""
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _SENSITIVE_KEYS or _contains_sensitive_payload(child):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_sensitive_payload(child) for child in value)
    return isinstance(value, str) and _SENSITIVE_TEXT.search(value) is not None


def _snapshot(event: RunStreamEventV1) -> RunStreamEventV1:
    """复制事件及其可变 JSON 容器，隔离历史和各订阅者。"""
    return RunStreamEventV1.model_validate(event.model_dump(mode="python"))


class EventSubscription(AsyncIterator[RunStreamEventV1]):
    """一个可显式关闭的 Run 实时订阅。"""

    def __init__(self, hub: EventHub, run_id: str) -> None:
        self._hub = hub
        self.run_id = run_id
        self._queue: asyncio.Queue[RunStreamEventV1] = asyncio.Queue()
        self._closed = False

    def __aiter__(self) -> EventSubscription:
        return self

    async def __anext__(self) -> RunStreamEventV1:
        if self._closed:
            raise StopAsyncIteration
        return await self._queue.get()

    async def aclose(self) -> None:
        """幂等关闭订阅并释放 Hub 中的引用。"""
        if self._closed:
            return
        self._closed = True
        self._hub._unsubscribe(self)


class EventHub:
    """提供历史回放、实时扇出和流终止记录的进程内事件 Hub。"""

    def __init__(self) -> None:
        self._history: dict[str, list[RunStreamEventV1]] = {}
        self._subscribers: dict[str, set[EventSubscription]] = {}
        self._closed_runs: set[str] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event: RunStreamEventV1) -> None:
        """按 Run 单调追加事件，并同步发送给当前订阅者。"""
        if not isinstance(event, RunStreamEventV1):
            raise TypeError("event 必须是 RunStreamEventV1")
        if _contains_sensitive_payload(event.payload):
            raise ValueError("事件 payload 包含禁止的敏感信息")
        async with self._lock:
            if event.run_id in self._closed_runs:
                raise ValueError("Run 事件流已经结束")
            history = self._history.setdefault(event.run_id, [])
            if history and event.sequence <= history[-1].sequence:
                raise ValueError("事件 sequence 必须递增")
            stored = _snapshot(event)
            history.append(stored)
            subscribers = tuple(self._subscribers.get(event.run_id, ()))
            if event.event == "stream_done":
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
        async with self._lock:
            if run_id in self._closed_runs:
                raise ValueError("Run 事件流已经结束")
            history = self._history.setdefault(run_id, [])
            stored = candidate.model_copy(
                update={"sequence": history[-1].sequence + 1 if history else 1}
            )
            stored = _snapshot(stored)
            history.append(stored)
            subscribers = tuple(self._subscribers.get(run_id, ()))
            if stored.event == "stream_done":
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
            return [
                _snapshot(event)
                for event in self._history.get(run_id, ())
                if event.sequence > after_sequence
            ]

    def subscribe(self, run_id: str) -> EventSubscription:
        """立即登记订阅，避免回放与实时监听之间丢失事件。"""
        _validate_run_id(run_id)
        subscription = EventSubscription(self, run_id)
        self._subscribers.setdefault(run_id, set()).add(subscription)
        return subscription

    def subscriber_count(self, run_id: str) -> int:
        """返回当前订阅数，供资源释放验证使用。"""
        return len(self._subscribers.get(run_id, ()))

    def is_closed(self, run_id: str) -> bool:
        """返回该 Run 是否已经发布 stream_done。"""
        return run_id in self._closed_runs

    def _unsubscribe(self, subscription: EventSubscription) -> None:
        subscribers = self._subscribers.get(subscription.run_id)
        if subscribers is None:
            return
        subscribers.discard(subscription)
        if not subscribers:
            self._subscribers.pop(subscription.run_id, None)


__all__ = ["EventHub", "EventSubscription"]
