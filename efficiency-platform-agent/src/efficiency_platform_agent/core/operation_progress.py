"""运营执行节点可选报告用户安全进度的异步窄端口。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal

OperationVisiblePhase = Literal[
    "understanding_request",
    "collecting_sources",
    "checking_evidence",
    "creating_content",
    "checking_delivery",
]
OperationProgressEvent = Literal[
    "phase_started",
    "research_started",
    "research_completed",
    "content_generation_started",
    "content_generation_completed",
    "quality_checked",
]
OperationProgressPublisher = Callable[
    [OperationProgressEvent, OperationVisiblePhase, Mapping[str, Any]], Awaitable[None]
]

_CURRENT_OPERATION_PROGRESS: ContextVar[OperationProgressPublisher | None] = ContextVar(
    "operation_progress_publisher", default=None
)


@contextmanager
def bind_operation_progress(
    publisher: OperationProgressPublisher,
) -> Iterator[None]:
    """把发布器绑定到当前异步上下文，并在退出时可靠恢复。"""

    if not callable(publisher):
        raise TypeError("publisher 必须可调用")
    token = _CURRENT_OPERATION_PROGRESS.set(publisher)
    try:
        yield
    finally:
        _CURRENT_OPERATION_PROGRESS.reset(token)


async def report_operation_progress(
    phase: OperationVisiblePhase,
    *,
    event: OperationProgressEvent = "phase_started",
    payload: Mapping[str, Any] | None = None,
) -> None:
    """存在当前 Run 发布器时报告真实节点进度，否则安全省略。"""

    publisher = _CURRENT_OPERATION_PROGRESS.get()
    if publisher is None:
        return
    await publisher(event, phase, dict(payload or {}))


__all__ = [
    "OperationProgressEvent",
    "OperationProgressPublisher",
    "OperationVisiblePhase",
    "bind_operation_progress",
    "report_operation_progress",
]
