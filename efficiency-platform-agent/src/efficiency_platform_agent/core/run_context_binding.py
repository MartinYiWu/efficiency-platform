"""可信运行作用域在异步任务间的显式绑定；不读取模型正文或 HTTP。"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import cast

from .memory import ConversationScope
from .memory_execution import MemoryExecutionContext


@dataclass(frozen=True, slots=True)
class RunContextBinding:
    conversation: ConversationScope
    task_id: str
    execution_id: str
    deadline_epoch_seconds: int
    memory_context: MemoryExecutionContext | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.conversation, ConversationScope):
            raise TypeError("CONTEXT_SCOPE_REQUIRED")
        for value in (self.task_id, self.execution_id):
            if type(value) is not str or not value.strip() or len(value) > 128:
                raise ValueError("CONTEXT_RUN_BINDING_INVALID")
        if (
            type(self.deadline_epoch_seconds) is not int
            or self.deadline_epoch_seconds <= 0
        ):
            raise ValueError("CONTEXT_DEADLINE_REQUIRED")
        if self.memory_context is not None:
            packet = self.memory_context.packet
            if (
                (packet.scope, packet.task_id, packet.execution_id)
                != (self.conversation, self.task_id, self.execution_id)
                or self.deadline_epoch_seconds
                > self.memory_context.deadline_epoch_seconds
            ):
                raise ValueError("MEMORY_RUN_BINDING_INVALID")


_current: ContextVar[RunContextBinding | None] = ContextVar(
    "context_run_binding", default=None
)


@contextmanager
def bind_run_context(binding: RunContextBinding | None) -> Iterator[None]:
    token = _current.set(binding)
    try:
        yield
    finally:
        _current.reset(token)


def current_run_context() -> RunContextBinding | None:
    return _current.get()


_conversation: ContextVar[ConversationScope | None] = ContextVar(
    "trusted_conversation_scope", default=None
)
_memory_context: ContextVar[MemoryExecutionContext | None] = ContextVar(
    "trusted_memory_context", default=None
)


@contextmanager
def bind_conversation_scope(
    scope: ConversationScope | None,
    *,
    memory_context: MemoryExecutionContext | None = None,
) -> Iterator[None]:
    if memory_context is not None and memory_context.packet.scope != scope:
        raise ValueError("MEMORY_SCOPE_MISMATCH")
    token = _conversation.set(scope)
    memory_token = _memory_context.set(memory_context)
    try:
        yield
    finally:
        _conversation.reset(token)
        _memory_context.reset(memory_token)


def current_conversation_scope() -> ConversationScope | None:
    return _conversation.get()


def current_memory_context() -> MemoryExecutionContext | None:
    return _memory_context.get()


_SCOPE_FIELDS = (
    "tenant_id",
    "user_id",
    "domain",
    "top_level_agent_id",
    "session_kind",
    "session_id",
)


def metadata_scope(scope: ConversationScope | None) -> dict[str, object]:
    memory = current_memory_context()
    return (
        {}
        if scope is None
        else {
            "context_scope": {name: getattr(scope, name) for name in _SCOPE_FIELDS},
            **({"memory_execution": memory.metadata()} if memory is not None else {}),
        }
    )


def binding_from_metadata(
    metadata: object, run_id: str, deadline_epoch_seconds: int
) -> RunContextBinding | None:
    from .run import JsonObject

    if isinstance(metadata, JsonObject):
        values: dict[str, object] = dict(metadata.items)
    elif isinstance(metadata, Mapping):
        values = dict(metadata)
    else:
        raise TypeError("CONTEXT_METADATA_INVALID")
    raw = values.get("context_scope")
    if raw is None:
        return None
    if isinstance(raw, JsonObject):
        scope_values: dict[str, object] = dict(raw.items)
    elif isinstance(raw, Mapping):
        scope_values = dict(cast(Mapping[str, object], raw))
    else:
        raise TypeError("CONTEXT_SCOPE_INVALID")
    if set(scope_values) != set(_SCOPE_FIELDS):
        raise ValueError("CONTEXT_SCOPE_INVALID")
    scope = ConversationScope(
        tenant_id=cast(str, scope_values["tenant_id"]),
        user_id=cast(str, scope_values["user_id"]),
        domain=cast(str, scope_values["domain"]),
        top_level_agent_id=cast(str, scope_values["top_level_agent_id"]),
        session_kind=cast(str, scope_values["session_kind"]),
        session_id=cast(str | None, scope_values["session_id"]),
    )
    raw_memory = values.get("memory_execution")
    if raw_memory is not None:
        memory = MemoryExecutionContext.from_metadata(raw_memory)
        return RunContextBinding(
            scope,
            memory.packet.task_id,
            memory.packet.execution_id,
            min(deadline_epoch_seconds, memory.deadline_epoch_seconds),
            memory,
        )
    return RunContextBinding(scope, run_id, run_id, deadline_epoch_seconds)
