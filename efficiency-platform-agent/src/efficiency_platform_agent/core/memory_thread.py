"""thread登记和恢复的中立端口；不包含运行框架或存储实现。"""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol

from .memory import ExecutionScope, SourceDependency, require_count, require_id


@dataclass(frozen=True, slots=True)
class ResumeRequest:
    wait_event_id: str
    packet_revision: int
    expected_execution_revision: int
    resume_request_id: str
    operation_hash: str
    mode: str
    new_content: bool = False

    def __post_init__(self) -> None:
        for value in (self.wait_event_id, self.resume_request_id):
            require_id(value)
        for count in (self.packet_revision, self.expected_execution_revision):
            require_count(count)
        if len(self.operation_hash) != 64 or any(
            value not in "0123456789abcdef" for value in self.operation_hash
        ):
            raise ValueError("RESUME_OPERATION_HASH_INVALID")
        if self.mode not in {"cpu", "paid", "refresh"}:
            raise ValueError("RESUME_MODE_INVALID")
        if self.new_content:
            raise ValueError("RESUME_NEW_CONTENT_DISABLED")


@dataclass(frozen=True, slots=True)
class ResumeReceipt:
    code: str
    receipt_ref: str


@dataclass(frozen=True, slots=True)
class ThreadCleanupReceipt:
    status: str
    receipt_ref: str | None = None


@dataclass(frozen=True, slots=True)
class CheckpointLocation:
    scope: ExecutionScope
    thread_id: str
    checkpoint_ns: str
    coordinate: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CheckpointCiphertext:
    ciphertext: bytes = field(repr=False)
    nonce: bytes = field(repr=False)
    key_version: str


class CheckpointBodyCipher(Protocol):
    def seal(
        self, location: CheckpointLocation, body: bytes
    ) -> CheckpointCiphertext: ...

    def open(
        self, location: CheckpointLocation, body: CheckpointCiphertext
    ) -> bytes: ...


class MemoryThreadRegistry(Protocol):
    def guard_execution(
        self,
        tenant_id: str,
        execution_id: str,
        backend_id: str,
        namespace: str,
    ) -> AbstractAsyncContextManager[CheckpointLocation]: ...

    def guard(
        self,
        thread_id: str,
        backend_id: str,
        namespace: str,
        *,
        pending_writes: bool = False,
    ) -> AbstractAsyncContextManager[CheckpointLocation]: ...

    async def enroll(self, scope: ExecutionScope, runtime_id: str) -> None: ...

    async def enroll_no_checkpoint(
        self, scope: ExecutionScope, runtime_id: str
    ) -> None: ...

    async def register_child(self, parent_thread_id: str, thread_id: str) -> None: ...

    async def check_runtime(self, runtime_id: str, tenant_id: str) -> None: ...

    async def resume(
        self, runtime_id: str, tenant_id: str, request: ResumeRequest
    ) -> ResumeReceipt: ...


class SourceEpochAuthority(Protocol):
    async def current(
        self, scope: ExecutionScope, dependencies: tuple[SourceDependency, ...]
    ) -> bool:
        """仅读取本机事件驱动epoch/tombstone技术视图；不得回调Java。"""
        ...

    async def revoked(
        self, scope: ExecutionScope, source: SourceDependency, event_id: str
    ) -> bool:
        """仅真实本机撤销事件及单调epoch变化可证明失效；未知和不可用拒绝。"""
        ...


class ThreadBackendInventory(Protocol):
    backend_id: str

    async def members(self, root_thread_id: str) -> frozenset[str]:
        """读取实际后端root及其保留前缀child；失败不得返回空集。"""
        ...

    async def entries(self, root_thread_id: str) -> frozenset[tuple[str, str, bool]]:
        """真实thread、namespace及pending-write存在性；仅读技术列。"""
        ...
