"""整 thread 遗忘的中立值与端口；可信登记簿负责授权和持久门禁。"""

from dataclasses import dataclass
from typing import Literal, Protocol

from .memory import ExecutionScope, SourceDependency


@dataclass(frozen=True, slots=True)
class CheckpointResidue:
    checkpoints: int
    blobs: int
    writes: int

    @property
    def empty(self) -> bool:
        return self.checkpoints == self.blobs == self.writes == 0


@dataclass(frozen=True, slots=True)
class ThreadBinding:
    thread_id: str
    parent_thread_id: str | None
    safety_dependencies: tuple[SourceDependency, ...]


@dataclass(frozen=True, slots=True)
class ThreadErasurePlan:
    scope: ExecutionScope
    operation_id: str
    execution_revision: int
    root_thread_id: str
    threads: tuple[ThreadBinding, ...]
    gate_state: str
    registry_complete: bool
    unique_owner: bool
    write_fenced: bool
    backend_ids: frozenset[str]
    fence_revision: int | None = None


Verification = tuple[tuple[str, str, CheckpointResidue], ...]


@dataclass(frozen=True, slots=True)
class ThreadErasureResult:
    status: Literal["DELETED", "DELETE_PENDING"]
    plan: ThreadErasurePlan
    verification: Verification = ()
    error_code: str | None = None


class ThreadErasureRegistry(Protocol):
    async def block_for_erasure(
        self, scope: ExecutionScope, source: SourceDependency
    ) -> ThreadErasurePlan | None:
        """鉴权后原子持久化 BLOCKED/REVOKED 并封锁保存、外发及 child 登记。

        返回服务端完整登记快照；每个 thread 均须证明全局唯一归属当前
        execution。无法证明全集、来源闭包或恢复 tombstone 时不得给出
        registry_complete。没有有效授权返回 None，不接收调用方 thread ID。
        """
        ...

    async def mark_deleted(
        self, plan: ThreadErasurePlan, verification: Verification
    ) -> bool:
        """核验 fence、完整线程集及原 revision 的 CAS；保留撤销/tombstone。

        仅在全部配置后端逐表为零时持久化 DELETED。失败保持门禁，不得
        把 DELETED 当作重新授权或解除 write fence。
        """
        ...


class ThreadCheckpointStore(Protocol):
    backend_id: str

    async def delete_thread(
        self, thread_id: str, tenant_id: str, *, authorization: ThreadErasurePlan
    ) -> None:
        """清理指定 thread 全部 namespace；返回前确保删除已提交。"""
        ...

    async def remaining(
        self, thread_id: str, tenant_id: str, *, authorization: ThreadErasurePlan
    ) -> CheckpointResidue:
        """读取真实后端三类状态数量，失败必须抛错，不能默认为零。"""
        ...
