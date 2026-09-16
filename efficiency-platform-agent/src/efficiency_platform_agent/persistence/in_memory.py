"""仅用于离线测试的进程内 Run 与事件适配器。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from efficiency_platform_agent.core.runtime import RunEventRecord, RunRecord


class InMemoryPersistenceError(ValueError):
    """进程内适配器写入冲突，携带稳定错误码。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(slots=True)
class InMemoryRunRepository:
    """以租户和 Run 双键隔离的异步内存仓储。"""

    _runs: dict[tuple[str, str], RunRecord] = field(default_factory=dict, init=False)
    _request_index: dict[tuple[str, str], str] = field(default_factory=dict, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def create(self, record: RunRecord) -> None:
        """原子创建 Run，重复 Run 或 request ID 均拒绝。"""
        key = (record.request.tenant_id, record.run_id)
        request_key = (record.request.tenant_id, record.request.request_id)
        async with self._lock:
            if key in self._runs or request_key in self._request_index:
                raise InMemoryPersistenceError(
                    "RUN_ALREADY_EXISTS", "Run 或 request_id 已存在"
                )
            self._runs[key] = record
            self._request_index[request_key] = record.run_id

    async def get(self, run_id: str, tenant_id: str) -> RunRecord | None:
        """按租户读取 Run，不存在或跨租户时返回 None。"""
        async with self._lock:
            return self._runs.get((tenant_id, run_id))

    async def get_by_request_id(
        self, request_id: str, tenant_id: str
    ) -> RunRecord | None:
        """按租户和幂等 request ID 读取 Run。"""
        async with self._lock:
            run_id = self._request_index.get((tenant_id, request_id))
            if run_id is None:
                return None
            return self._runs.get((tenant_id, run_id))

    async def save(self, record: RunRecord, expected_version: int) -> None:
        """使用版本 CAS 原子替换 Run 快照。"""
        if not isinstance(expected_version, int) or isinstance(expected_version, bool):
            raise InMemoryPersistenceError("RUN_VERSION_CONFLICT", "版本条件无效")
        key = (record.request.tenant_id, record.run_id)
        request_key = (record.request.tenant_id, record.request.request_id)
        async with self._lock:
            current = self._runs.get(key)
            if (
                current is None
                or current.version != expected_version
                or record.version != expected_version + 1
                or self._request_index.get(request_key) != record.run_id
            ):
                raise InMemoryPersistenceError("RUN_VERSION_CONFLICT", "Run 版本冲突")
            self._runs[key] = record


@dataclass(slots=True)
class InMemoryRunEventStore:
    """按租户和 Run 隔离、严格递增序号的异步事件存储。"""

    _events: dict[tuple[str, str], list[RunEventRecord]] = field(
        default_factory=dict, init=False
    )
    _event_ids: set[str] = field(default_factory=set, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def append(self, event: RunEventRecord) -> None:
        """校验唯一 ID 和连续序号后原子追加事件。"""
        key = (event.tenant_id, event.run_id)
        async with self._lock:
            if event.event_id in self._event_ids:
                raise InMemoryPersistenceError("EVENT_ID_CONFLICT", "事件 ID 已存在")
            events = self._events.get(key)
            expected_sequence = 1 if not events else events[-1].sequence + 1
            if event.sequence != expected_sequence:
                raise InMemoryPersistenceError(
                    "EVENT_SEQUENCE_CONFLICT", "事件序号不连续"
                )
            # 先校验全部条件，再替换列表，避免半写入状态。
            replacement = [] if events is None else list(events)
            replacement.append(event)
            self._events[key] = replacement
            self._event_ids.add(event.event_id)

    async def list_after(
        self, run_id: str, tenant_id: str, after_sequence: int
    ) -> tuple[RunEventRecord, ...]:
        """返回严格晚于游标的不可变事件快照。"""
        if (
            not isinstance(after_sequence, int)
            or isinstance(after_sequence, bool)
            or after_sequence < 0
        ):
            raise ValueError("after_sequence 必须是非负整数")
        async with self._lock:
            events = self._events.get((tenant_id, run_id), ())
            return tuple(event for event in events if event.sequence > after_sequence)


@dataclass(frozen=True, slots=True)
class FixedClock:
    """返回固定毫秒时间的确定性时钟。"""

    epoch_ms: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.epoch_ms, int)
            or isinstance(self.epoch_ms, bool)
            or self.epoch_ms < 0
        ):
            raise ValueError("epoch_ms 必须是非负整数")

    def now_epoch_ms(self) -> int:
        """返回固定时间。"""
        return self.epoch_ms


@dataclass(slots=True)
class SequenceIdGenerator:
    """为 Run 和事件分别生成可复现的递增标识。"""

    run_prefix: str = "run"
    event_prefix: str = "event"
    _run_sequence: int = field(default=0, init=False)
    _event_sequence: int = field(default=0, init=False)

    def new_run_id(self) -> str:
        """生成下一个 Run ID。"""
        self._run_sequence += 1
        return f"{self.run_prefix}-{self._run_sequence}"

    def new_event_id(self) -> str:
        """生成下一个事件 ID。"""
        self._event_sequence += 1
        return f"{self.event_prefix}-{self._event_sequence}"
