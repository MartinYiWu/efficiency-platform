"""最终付费发送门禁的中立异步上下文。"""

from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Protocol


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
