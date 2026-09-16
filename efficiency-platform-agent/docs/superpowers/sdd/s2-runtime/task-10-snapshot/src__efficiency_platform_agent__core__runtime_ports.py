"""Run 与事件存储、时钟和标识生成的异步端口。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from .runtime import RunEventRecord, RunRecord


@runtime_checkable
class RunRepository(Protocol):
    """Run 权威快照读写端口。"""

    async def create(self, record: RunRecord) -> None:
        raise NotImplementedError

    async def get(self, run_id: str, tenant_id: str) -> RunRecord | None:
        raise NotImplementedError

    async def get_by_request_id(self, request_id: str, tenant_id: str) -> RunRecord | None:
        raise NotImplementedError

    async def save(self, record: RunRecord, expected_version: int) -> None:
        raise NotImplementedError


@runtime_checkable
class RunEventStore(Protocol):
    """Run 事件追加与游标回放端口。"""

    async def append(self, event: RunEventRecord) -> None:
        raise NotImplementedError

    async def list_after(self, run_id: str, tenant_id: str, after_sequence: int) -> Sequence[RunEventRecord]:
        raise NotImplementedError


@runtime_checkable
class Clock(Protocol):
    """提供可替换的毫秒时钟。"""

    def now_epoch_ms(self) -> int:
        raise NotImplementedError


@runtime_checkable
class IdGenerator(Protocol):
    """生成 Run 与事件标识。"""

    def new_run_id(self) -> str:
        raise NotImplementedError

    def new_event_id(self) -> str:
        raise NotImplementedError
