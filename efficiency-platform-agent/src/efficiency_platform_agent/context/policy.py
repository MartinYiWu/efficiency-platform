"""节点发布策略与不可分割的模型消息组；均为不可变服务端值。"""

from dataclasses import dataclass, field

from efficiency_platform_agent.core.memory import (
    ExecutionScope,
    SourceDependency,
    require_bool,
    require_count,
    require_dependencies,
    require_id,
    require_ids,
)
from efficiency_platform_agent.core.run import ProviderMessage

REQUIRED_KINDS = frozenset(
    {
        "system",
        "current_request",
        "business_evidence",
        "object_version",
        "negation",
        "receipt",
        "tool_group",
        "rule",
        "frozen_date",
    }
)
KINDS = REQUIRED_KINDS | {"history", "memory", "summary", "capsule", "optional"}


@dataclass(frozen=True, slots=True)
class ContextPolicy:
    node_id: str
    version: str
    scope: ExecutionScope
    authorized_dependencies: tuple[SourceDependency, ...] = ()
    allowed_message_ids: frozenset[str] = frozenset()
    max_pieces: int = 256
    max_history_messages: int = 12
    history_token_limit: int = 6000
    memory_token_limit: int = 2048
    summary_token_limit: int = 1000
    capsule_token_limit: int = 1000

    def __post_init__(self) -> None:
        require_id(self.node_id)
        require_id(self.version)
        if not isinstance(self.scope, ExecutionScope):
            raise TypeError("CONTEXT_SCOPE_INVALID")
        require_dependencies(self.authorized_dependencies)
        require_ids(self.allowed_message_ids)
        for count in (
            self.max_pieces,
            self.max_history_messages,
            self.history_token_limit,
            self.memory_token_limit,
            self.summary_token_limit,
            self.capsule_token_limit,
        ):
            require_count(count)


@dataclass(frozen=True, slots=True)
class ContextPiece:
    piece_id: str
    scope: ExecutionScope
    messages: tuple[ProviderMessage, ...] = field(repr=False)
    safety_dependencies: tuple[SourceDependency, ...] = ()
    required: bool = False
    priority: int = 0
    kind: str = "optional"
    covered_message_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_id(self.piece_id)
        if not isinstance(self.scope, ExecutionScope):
            raise TypeError("CONTEXT_SCOPE_INVALID")
        if (
            type(self.messages) is not tuple
            or not self.messages
            or any(
                not isinstance(message, ProviderMessage) for message in self.messages
            )
        ):
            raise ValueError("CONTEXT_MESSAGES_INVALID")
        require_dependencies(self.safety_dependencies)
        require_bool(self.required)
        require_count(self.priority)
        if self.kind not in KINDS:
            raise ValueError("CONTEXT_KIND_INVALID")
        if type(self.covered_message_ids) is not tuple:
            raise ValueError("CONTEXT_COVERAGE_INVALID")
        for identifier in self.covered_message_ids:
            require_id(identifier)
        if len(set(self.covered_message_ids)) != len(self.covered_message_ids):
            raise ValueError("CONTEXT_COVERAGE_INVALID")
        pending: set[str] = set()
        seen: set[str] = set()
        for message in self.messages:
            if pending and message.role != "tool":
                raise ValueError("CONTEXT_TOOL_GROUP_INVALID")
            for call in message.tool_calls:
                if call.tool_call_id in seen:
                    raise ValueError("CONTEXT_TOOL_GROUP_INVALID")
                pending.add(call.tool_call_id)
                seen.add(call.tool_call_id)
            if message.role == "tool":
                if message.tool_call_id not in pending:
                    raise ValueError("CONTEXT_TOOL_GROUP_INVALID")
                pending.remove(message.tool_call_id)
        if pending:
            raise ValueError("CONTEXT_TOOL_GROUP_INVALID")

    @property
    def is_required(self) -> bool:
        return (
            self.required
            or self.kind in REQUIRED_KINDS
            or any(
                message.role in {"system", "developer", "tool"} or message.tool_calls
                for message in self.messages
            )
        )
