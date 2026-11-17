"""上下文持久化、实时授权与操作身份的中立端口。"""

from dataclasses import dataclass
from typing import Protocol

from .context_control import ContextManifest, ModelCapacity, WindowLimits
from .memory import (
    ExecutionScope,
    MemoryContextPacket,
    SourceDependency,
    require_bool,
    require_count,
    require_id,
)
from .run import JsonObject


@dataclass(frozen=True, slots=True)
class ContextOperation:
    operation_id: str
    attempt: int
    deadline_epoch_seconds: int
    memory_disabled: bool

    def __post_init__(self) -> None:
        require_id(self.operation_id)
        require_count(self.attempt)
        if not 1 <= self.attempt <= 3:
            raise ValueError("CONTEXT_ATTEMPT_INVALID")
        require_count(self.deadline_epoch_seconds)
        require_bool(self.memory_disabled)


@dataclass(frozen=True, slots=True)
class ContextMetadata:
    node_id: str
    policy_version: str
    prompt_version: str
    tool_version: str
    output_schema_version: str
    ctx_revision: int
    capacity: ModelCapacity
    limits: WindowLimits
    options: JsonObject

    def __post_init__(self) -> None:
        for value in (
            self.node_id,
            self.policy_version,
            self.prompt_version,
            self.tool_version,
            self.output_schema_version,
        ):
            require_id(value)
        require_count(self.ctx_revision)
        if (
            not isinstance(self.capacity, ModelCapacity)
            or not isinstance(self.limits, WindowLimits)
            or not isinstance(self.options, JsonObject)
        ):
            raise TypeError("CONTEXT_METADATA_INVALID")


@dataclass(frozen=True, slots=True)
class OperationReceipt:
    input_hash: str
    status: str
    deadline_epoch_seconds: int
    receipt_ref: str | None = None
    latest_attempt: int = 1

    def __post_init__(self) -> None:
        require_count(self.latest_attempt)
        if not 1 <= self.latest_attempt <= 3:
            raise ValueError("CONTEXT_ATTEMPT_INVALID")
        require_id(self.input_hash)
        require_count(self.deadline_epoch_seconds)
        if self.status not in {"NOT_SENT", "SENT", "SUCCEEDED", "UNKNOWN"}:
            raise ValueError("CONTEXT_RECEIPT_INVALID")
        if self.receipt_ref is not None:
            require_id(self.receipt_ref)


class MemoryPacketValidator(Protocol):
    async def validate(
        self,
        scope: ExecutionScope,
        packet: MemoryContextPacket | None,
        dependencies: tuple[SourceDependency, ...],
        operation: ContextOperation,
    ) -> None: ...


class ContextManifestStore(Protocol):
    async def save_manifest_once(
        self, manifest: ContextManifest, operation: ContextOperation
    ) -> ContextManifest: ...
    async def get_operation_receipt(
        self, scope: ExecutionScope, operation_id: str
    ) -> OperationReceipt | None: ...
    async def mark_sending(
        self, manifest: ContextManifest, operation: ContextOperation
    ) -> bool: ...
    async def record_receipt(
        self, manifest: ContextManifest, status: str, receipt_ref: str | None = None
    ) -> bool: ...
