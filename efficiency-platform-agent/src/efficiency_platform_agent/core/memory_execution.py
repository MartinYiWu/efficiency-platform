"""内部认证完成后保存的原执行授权；不从模型或公开请求解析权限。"""

from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from .memory import (
    ConversationScope,
    ExecutionScope,
    MemoryContextPacket,
    MemoryPolicy,
    MemoryReference,
    SourceDependency,
    require_id,
)
from .run import JsonObject


@dataclass(frozen=True, slots=True)
class MemoryExecutionGrant:
    node_id: str
    execution_agent_id: str
    purpose: str

    def __post_init__(self) -> None:
        for value in (self.node_id, self.execution_agent_id, self.purpose):
            require_id(value)


@dataclass(frozen=True, slots=True)
class MemoryExecutionContext:
    packet: MemoryContextPacket = field(repr=False)
    policy: MemoryPolicy
    execution_grants: tuple[MemoryExecutionGrant, ...]
    deadline_epoch_seconds: int
    packet_digest: str
    semantic_snapshot_digest: str
    request_digest: str
    input_dependencies: tuple[SourceDependency, ...] = ()
    summary_context_json: str | None = field(default=None, repr=False)
    derive_template_json: str | None = field(default=None, repr=False)
    knowledge_context_json: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.packet, MemoryContextPacket) or not isinstance(
            self.policy, MemoryPolicy
        ):
            raise TypeError("MEMORY_EXECUTION_INVALID")
        if (
            not self.policy.enabled
            or self.policy.domain != self.packet.scope.domain
            or self.policy.version != self.packet.policy_version
            or self.packet.scope.top_level_agent_id not in self.policy.agent_ids
            or type(self.deadline_epoch_seconds) is not int
            or self.deadline_epoch_seconds < self.packet.expires_at
        ):
            raise ValueError("MEMORY_EXECUTION_INVALID")
        if (
            not self.execution_grants
            or len({grant.node_id for grant in self.execution_grants})
            != len(self.execution_grants)
            or any(
                grant.execution_agent_id not in self.policy.agent_ids
                for grant in self.execution_grants
            )
        ):
            raise ValueError("MEMORY_EXECUTION_GRANT_INVALID")
        if type(self.input_dependencies) is not tuple or not set(
            self.input_dependencies
        ).issubset(self.packet.safety_dependencies):
            raise ValueError("MEMORY_INPUT_DEPENDENCIES_INVALID")
        for snapshot in (
            self.summary_context_json,
            self.derive_template_json,
            self.knowledge_context_json,
        ):
            if snapshot is not None and (
                type(snapshot) is not str
                or not snapshot
                or len(snapshot.encode("utf-8")) > 524288
            ):
                raise ValueError("MEMORY_SUMMARY_CONTEXT_INVALID")
        for digest in (
            self.packet_digest,
            self.semantic_snapshot_digest,
            self.request_digest,
        ):
            if (
                type(digest) is not str
                or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise ValueError("MEMORY_DIGEST_INVALID")

    def metadata(self) -> dict[str, Any]:
        def plain(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: plain(child) for key, child in value.items()}
            if isinstance(value, frozenset):
                return sorted(value)
            if isinstance(value, (tuple, list)):
                return [plain(child) for child in value]
            return value

        data = asdict(self)
        if self.summary_context_json is None:
            data.pop("summary_context_json")
        if self.derive_template_json is None:
            data.pop("derive_template_json")
        if self.knowledge_context_json is None:
            data.pop("knowledge_context_json")
        return plain(data)

    @classmethod
    def from_metadata(cls, value: object) -> "MemoryExecutionContext":
        def plain(item: Any) -> Any:
            if isinstance(item, JsonObject):
                return {key: plain(child) for key, child in item.items}
            if isinstance(item, Mapping):
                return {key: plain(child) for key, child in item.items()}
            if isinstance(item, (tuple, list)):
                return [plain(child) for child in item]
            return item

        data = plain(value)
        if not isinstance(data, dict):
            raise TypeError("MEMORY_EXECUTION_METADATA_INVALID")
        packet = dict(data.pop("packet"))
        packet["scope"] = ConversationScope(**packet["scope"])
        packet["safety_dependencies"] = tuple(
            SourceDependency(**dep) for dep in packet["safety_dependencies"]
        )
        packet["items"] = tuple(
            MemoryReference(
                **(
                    item
                    | {
                        "safety_dependencies": tuple(
                            SourceDependency(**dep)
                            for dep in item["safety_dependencies"]
                        )
                    }
                )
            )
            for item in packet["items"]
        )
        policy = dict(data.pop("policy"))
        for key in (
            "agent_ids",
            "readable_layers",
            "writable_kinds",
            "allowed_scopes",
            "field_allowlist",
            "sensitivity_levels",
            "source_types",
        ):
            policy[key] = frozenset(policy[key])
        grants = tuple(
            MemoryExecutionGrant(**grant) for grant in data.pop("execution_grants")
        )
        data["input_dependencies"] = tuple(
            SourceDependency(**dep) for dep in data.get("input_dependencies", ())
        )
        return cls(
            packet=MemoryContextPacket(**packet),
            policy=MemoryPolicy(**policy),
            execution_grants=grants,
            **data,
        )


@dataclass(frozen=True, slots=True)
class MemoryExecutionRecord:
    context: MemoryExecutionContext = field(repr=False)
    runtime_id: str
    runtime_kind: str
    request_fingerprint: str
    deadline_epoch_seconds: int
    state: str
    execution_revision: int
    grant_epoch: int
    source_epoch: int
    deletion_epoch: int
    key_version: str | None = None


@dataclass(frozen=True, slots=True)
class MemorySendPermit:
    scope: ExecutionScope
    runtime_id: str
    operation_id: str
    attempt: int
    input_hash: str
    manifest_id: str
    packet_id: str
    packet_revision: int
    packet_digest: str
    execution_revision: int
    deadline_epoch_seconds: int
    permit_ref: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise TypeError("MEMORY_SEND_PERMIT_INVALID")
        for value in (
            self.runtime_id,
            self.operation_id,
            self.manifest_id,
            self.packet_id,
            self.permit_ref,
        ):
            require_id(value)
        for count in (
            self.attempt,
            self.packet_revision,
            self.execution_revision,
            self.deadline_epoch_seconds,
        ):
            if type(count) is not int or count <= 0:
                raise ValueError("MEMORY_SEND_PERMIT_INVALID")
        if self.attempt > 3:
            raise ValueError("MEMORY_SEND_PERMIT_INVALID")
        for digest in (self.input_hash, self.packet_digest):
            if len(digest) != 64 or any(
                char not in "0123456789abcdef" for char in digest
            ):
                raise ValueError("MEMORY_SEND_PERMIT_INVALID")


class MemorySendPermitAuthority(Protocol):
    async def validate(self, permit: MemorySendPermit) -> bool: ...


@dataclass(frozen=True, slots=True)
class MemoryWaitCheckpointCapability:
    scope: ExecutionScope
    runtime_id: str
    wait_event_id: str
    operation_id: str
    attempt: int
    canonical_request_hmac: str | None
    packet_revision: int
    execution_revision: int
    current_context_fingerprint: str
    original_deadline: int
    capability_ref: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise TypeError("MEMORY_WAIT_CAPABILITY_INVALID")
        for value in (
            self.runtime_id,
            self.wait_event_id,
            self.operation_id,
            self.capability_ref,
        ):
            require_id(value)
        for count in (
            self.attempt,
            self.packet_revision,
            self.execution_revision,
            self.original_deadline,
        ):
            if type(count) is not int or count <= 0:
                raise ValueError("MEMORY_WAIT_CAPABILITY_INVALID")
        if self.attempt > 3:
            raise ValueError("MEMORY_WAIT_CAPABILITY_INVALID")
        for digest in (self.current_context_fingerprint, self.canonical_request_hmac):
            if digest is not None and (
                len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise ValueError("MEMORY_WAIT_CAPABILITY_INVALID")


@dataclass(frozen=True, slots=True)
class MemoryGraphResumeCapability:
    binding: MemoryWaitCheckpointCapability
    receipt_ref: str
    checkpoint_ns: str
    checkpoint_id: str
    target_packet_revision: int
    target_context_fingerprint: str
    capability_ref: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.binding, MemoryWaitCheckpointCapability):
            raise TypeError("MEMORY_RESUME_CAPABILITY_INVALID")
        for value in (self.receipt_ref, self.checkpoint_id, self.capability_ref):
            require_id(value)
        if self.checkpoint_ns != "":
            require_id(self.checkpoint_ns)
        if (
            type(self.target_packet_revision) is not int
            or self.target_packet_revision <= self.binding.packet_revision
        ):
            raise ValueError("MEMORY_RESUME_CAPABILITY_INVALID")
        if len(self.target_context_fingerprint) != 64 or any(
            char not in "0123456789abcdef" for char in self.target_context_fingerprint
        ):
            raise ValueError("MEMORY_RESUME_CAPABILITY_INVALID")


_wait_checkpoint_capability: ContextVar[MemoryWaitCheckpointCapability | None] = (
    ContextVar("memory_wait_checkpoint_capability", default=None)
)


def current_memory_wait_checkpoint_capability() -> (
    MemoryWaitCheckpointCapability | None
):
    return _wait_checkpoint_capability.get()


@contextmanager
def bind_memory_wait_checkpoint_capability(capability: MemoryWaitCheckpointCapability):
    token = _wait_checkpoint_capability.set(capability)
    try:
        yield capability
    finally:
        _wait_checkpoint_capability.reset(token)


_result_checkpoint_permit: ContextVar[MemorySendPermit | None] = ContextVar(
    "memory_result_checkpoint_permit", default=None
)


def current_memory_result_checkpoint_permit() -> MemorySendPermit | None:
    return _result_checkpoint_permit.get()


@contextmanager
def bind_memory_result_checkpoint_permit(permit: MemorySendPermit):
    token = _result_checkpoint_permit.set(permit)
    try:
        yield permit
    finally:
        _result_checkpoint_permit.reset(token)


@dataclass(frozen=True, slots=True)
class MemoryInvalidation:
    tenant_id: str
    execution_id: str
    event_id: str
    expected_execution_revision: int
    grant_epoch: int
    source_epoch: int
    deletion_epoch: int

    def __post_init__(self) -> None:
        for value in (self.tenant_id, self.execution_id, self.event_id):
            require_id(value)
        for count in (
            self.expected_execution_revision,
            self.grant_epoch,
            self.source_epoch,
            self.deletion_epoch,
        ):
            if type(count) is not int or count < 0:
                raise ValueError("MEMORY_INVALIDATION_INVALID")


class MemoryExecutionStore(Protocol):
    async def claim(
        self,
        context: MemoryExecutionContext,
        runtime_id: str,
        runtime_kind: str,
        request_fingerprint: str,
        budget_deadline: int,
    ) -> tuple[MemoryExecutionRecord, bool]: ...

    async def get(
        self, tenant_id: str, execution_id: str
    ) -> MemoryExecutionRecord | None: ...

    async def invalidate(self, event: MemoryInvalidation) -> str: ...


def memory_operation_deadline_matches(
    node_id: str, deadline: int, original: int
) -> bool:
    """原操作截止不改；已核原帧的派生只可收紧，其他节点仍精确相等。"""
    return (
        type(deadline) is int
        and type(original) is int
        and deadline > 0
        and (
            deadline <= original if node_id == "memory.derive" else deadline == original
        )
    )
