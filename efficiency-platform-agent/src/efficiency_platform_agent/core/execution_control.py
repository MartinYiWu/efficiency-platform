"""同一任务共享逻辑操作、停止信号及实际HTTP尝试额度。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from time import monotonic
from typing import Any, TypeVar

from .paid_budget import PaidBudgetError

MAX_RUN_CALLS = 60
MAX_RUN_COST_MICROUNITS = 100_000_000
MAX_RUN_DURATION_MS = 600_000
MAX_OPERATION_ATTEMPTS = 3
MAX_NO_PROGRESS = 3

T = TypeVar("T")


@dataclass
class _Operation:
    key: str = ""
    attempts: int = 0
    failures: int = 0


_current_run: ContextVar[RunControl | None] = ContextVar("execution_run", default=None)
_current_operation: ContextVar[_Operation | None] = ContextVar(
    "execution_operation", default=None
)


class RunControl:
    def __init__(self, *, timeout_ms: int = MAX_RUN_DURATION_MS) -> None:
        self.deadline = monotonic() + min(timeout_ms, MAX_RUN_DURATION_MS) / 1000
        self.stopped: str | None = None
        self.calls = 0
        self.replays = 0
        self.results: dict[str, Any] = {}
        self.pending: dict[str, asyncio.Task[Any]] = {}
        self.operations: dict[str, _Operation] = {}
        self.http_tasks: dict[object, asyncio.Task[Any]] = {}
        self.streams: dict[object, Callable[[], Awaitable[None]]] = {}

    def stop(self, code: str = "AGENT_TASK_STOPPED") -> None:
        if self.stopped is None:
            self.stopped = code

    def check(self) -> None:
        if monotonic() >= self.deadline:
            self.stop("AGENT_TASK_DEADLINE")
        if self.stopped is not None:
            raise PaidBudgetError(self.stopped, "任务已停止，未继续调用")

    async def execute(
        self,
        key: str,
        work: Callable[[], Awaitable[T]],
        *,
        recoverable_codes: frozenset[str] = frozenset(),
    ) -> T:
        self.check()
        if key in self.results:
            self.replays += 1
            if self.replays >= MAX_NO_PROGRESS:
                self.stop("AGENT_NO_PROGRESS")
                self.check()
            return self.results[key]
        if key not in self.pending:
            if key not in self.operations and len(self.operations) >= MAX_RUN_CALLS:
                self.stop("AGENT_WORK_LIMIT_EXCEEDED")
                self.check()
            operation = self.operations.setdefault(key, _Operation(key))
            if operation.failures >= MAX_OPERATION_ATTEMPTS:
                self.stop("AGENT_OPERATION_ATTEMPTS_EXHAUSTED")
                self.check()

            async def invoke() -> T:
                with execution_scope(self):
                    token = _current_operation.set(operation)
                    try:
                        self.check()
                        value = await work()
                        self.check()
                        self.results[key] = value
                        self.replays = 0
                        return value
                    except BaseException as error:
                        operation.failures += 1
                        if getattr(error, "code", None) not in recoverable_codes:
                            self.stop()
                        raise
                    finally:
                        _current_operation.reset(token)

            self.pending[key] = asyncio.create_task(invoke())
        task = self.pending[key]
        try:
            # 单个订阅者断开不取消共享工作；整个任务由close统一取消。
            return await asyncio.shield(task)
        finally:
            if task.done() and self.pending.get(key) is task:
                self.pending.pop(key, None)

    async def close(self) -> None:
        self.stop()
        tasks = tuple(
            (set(self.pending.values()) | set(self.http_tasks.values()))
            - {asyncio.current_task()}
        )
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(
            *(close() for close in tuple(self.streams.values())), return_exceptions=True
        )
        self.pending.clear()
        self.http_tasks.clear()
        self.streams.clear()

    def consume_attempt(self, operation_key: str | None) -> None:
        """持久执行控制可扩展此发送前门禁；普通任务仍使用本地有界计数。"""
        del operation_key


@contextmanager
def execution_scope(control: RunControl) -> Iterator[RunControl]:
    token = _current_run.set(control)
    try:
        yield control
    finally:
        _current_run.reset(token)


def current_run_control() -> RunControl | None:
    return _current_run.get()


def current_operation_key() -> str | None:
    operation = _current_operation.get()
    return None if operation is None else operation.key


def consume_http_attempt() -> None:
    control = _current_run.get()
    if control is None:
        return
    control.check()
    operation = _current_operation.get()
    if operation is not None and operation.attempts >= MAX_OPERATION_ATTEMPTS:
        control.stop("AGENT_OPERATION_ATTEMPTS_EXHAUSTED")
    if control.calls >= MAX_RUN_CALLS:
        control.stop("AGENT_CALL_LIMIT_EXCEEDED")
    control.check()
    if operation is not None:
        control.consume_attempt(operation.key)
        operation.attempts += 1
    else:
        control.consume_attempt(None)
    control.calls += 1
