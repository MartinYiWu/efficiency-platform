"""受信CPU清理的技术回执端口；Java仍是唯一业务任务真相。"""

from collections.abc import Awaitable, Callable
from typing import Protocol

from .memory import SourceDependency
from .memory_execution import MemoryExecutionRecord, MemoryInvalidation


class MemoryCleanupJournal(Protocol):
    runtime_scrubber: Callable[[MemoryExecutionRecord], Awaitable[bool]] | None
    async def revoke(self, event: MemoryInvalidation, dependencies: tuple[SourceDependency, ...], record: MemoryExecutionRecord) -> str: ...
    async def receipts(
        self, event: MemoryInvalidation, dependencies: tuple[SourceDependency, ...]
    ) -> dict[str, str]: ...

    async def confirm(
        self,
        event: MemoryInvalidation,
        dependencies: tuple[SourceDependency, ...],
        target: str,
        receipt: str,
    ) -> None: ...

    async def scrub(
        self,
        event: MemoryInvalidation,
        dependencies: tuple[SourceDependency, ...],
        record: MemoryExecutionRecord,
    ) -> str | None: ...
