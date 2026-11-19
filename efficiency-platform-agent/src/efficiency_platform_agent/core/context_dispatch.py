"""最终付费发送门禁的中立异步上下文。"""

from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import AbstractAsyncContextManager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Protocol


class ResultPublishDenied(PermissionError):
    code = "MEMORY_RESULT_PUBLISH_DENIED"


class ResultPublishGuard(Protocol):
    async def check(self, run_id: str) -> None: ...


_result_publish_guard: ContextVar[ResultPublishGuard | None] = ContextVar(
    "result_publish_guard", default=None
)
_result_publish_required: ContextVar[bool] = ContextVar(
    "result_publish_required", default=False
)


def current_result_publish_guard() -> ResultPublishGuard | None:
    return _result_publish_guard.get()


def result_publish_guard_required() -> bool:
    return _result_publish_required.get()


@contextmanager
def require_result_publish_guard() -> Iterator[None]:
    token = _result_publish_required.set(True)
    try:
        yield
    finally:
        _result_publish_required.reset(token)


@contextmanager
def bind_result_publish_guard(guard: ResultPublishGuard) -> Iterator[None]:
    token = _result_publish_guard.set(guard)
    try:
        with require_result_publish_guard():
            yield
    finally:
        _result_publish_guard.reset(token)


class ContextSendLease(Protocol):
    def acquire(self) -> AbstractAsyncContextManager[object]: ...


_send_lease: ContextVar[ContextSendLease | None] = ContextVar(
    "context_send_lease", default=None
)


@contextmanager
def bind_context_send_lease(lease: ContextSendLease) -> Iterator[None]:
    token = _send_lease.set(lease)
    try:
        yield
    finally:
        _send_lease.reset(token)


def current_context_send_lease() -> ContextSendLease | None:
    return _send_lease.get()


class ContextSendGuard(Protocol):
    async def before_send(self, payload: Mapping[str, object]) -> None: ...
    def check_live(self) -> None: ...


_guard: ContextVar[ContextSendGuard | None] = ContextVar(
    "context_send_guard", default=None
)


@contextmanager
def bind_context_send_guard(guard: ContextSendGuard) -> Iterator[None]:
    token = _guard.set(guard)
    try:
        yield
    finally:
        _guard.reset(token)


def current_context_send_guard() -> ContextSendGuard | None:
    return _guard.get()


@dataclass(slots=True)
class ModelStage:
    stage_id: str
    semantic_input: bytes = field(repr=False)
    node_id: str = "model"
    subtask_id: str | None = None
    allow_repair: Callable[[], Awaitable[None]] | None = field(default=None, repr=False)
    complete: Callable[[], Awaitable[None]] | None = field(default=None, repr=False)


_stage: ContextVar[ModelStage | None] = ContextVar("context_model_stage", default=None)


@contextmanager
def model_stage(
    stage_id: str,
    semantic_input: bytes,
    *,
    node_id: str = "model",
    subtask_id: str | None = None,
) -> Iterator[ModelStage]:
    parent = _stage.get()
    stage = ModelStage(
        stage_id,
        semantic_input,
        node_id,
        subtask_id
        if subtask_id is not None
        else (parent.subtask_id if parent else None),
    )
    token = _stage.set(stage)
    try:
        yield stage
    finally:
        _stage.reset(token)


def current_model_stage() -> ModelStage | None:
    return _stage.get()


async def allow_context_repair() -> None:
    stage = current_model_stage()
    if stage is not None and stage.allow_repair is not None:
        await stage.allow_repair()
