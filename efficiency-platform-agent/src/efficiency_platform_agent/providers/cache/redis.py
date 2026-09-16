"""S7 Redis Streams 的短期事件适配器。

本模块只依赖注入的 Redis 协议对象。构造适配器不会创建客户端，也不会
主动连接外部服务；长期运行事实仍由 S2 的权威存储负责。
"""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from ...core.enums import RunStatus
from ...core.run import JsonObject, JsonValue
from ...core.runtime import RunEventRecord

_STAMP = re.compile(r"^[A-Za-z0-9_-]{1,96}$")


async def _call(client: Any, name: str, *args: Any, **kwargs: Any) -> Any:
    """调用注入客户端的方法，并兼容同步协议 Stub。"""
    method = getattr(client, name, None)
    if method is None:
        return None
    result = method(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _plain(value: Any) -> Any:
    """将 S2 不可变 JSON 值转换为可编码的普通值。"""
    if hasattr(value, "items") and not isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def _decode_text(value: object) -> str:
    """将 Redis 字节字段安全转换为文本。"""

    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, str):
        return value
    raise ValueError("REDIS_EVENT_FORMAT_INVALID")


def _json_value(value: object) -> JsonValue:
    """把 Redis JSON 载荷转换为核心不可变 JSON 值。"""

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return JsonObject(
            tuple((str(key), _json_value(item)) for key, item in value.items())
        )
    if isinstance(value, list):
        return tuple(_json_value(item) for item in value)
    raise ValueError("REDIS_EVENT_FORMAT_INVALID")


def _parse_stream_row(row: object) -> RunEventRecord:
    """将 Redis Stream 行解析为 S2 事件事实。"""

    if not isinstance(row, Sequence) or isinstance(row, (str, bytes)) or len(row) < 2:
        raise ValueError("REDIS_EVENT_FORMAT_INVALID")
    raw_fields = row[1]
    if not isinstance(raw_fields, Mapping):
        raise TypeError("REDIS_EVENT_FORMAT_INVALID")
    fields = {_decode_text(key): value for key, value in raw_fields.items()}
    required = {
        "event_id",
        "event_type",
        "run_id",
        "tenant_id",
        "sequence",
        "occurred_at_epoch_ms",
        "status",
        "payload",
    }
    if set(fields) != required:
        raise ValueError("REDIS_EVENT_FORMAT_INVALID")
    try:
        payload_raw = _decode_text(fields["payload"])
        payload_value = _json_value(json.loads(payload_raw))
        if not isinstance(payload_value, JsonObject):
            raise TypeError("REDIS_EVENT_FORMAT_INVALID")
        return RunEventRecord(
            event_id=_decode_text(fields["event_id"]),
            event_type=_decode_text(fields["event_type"]),
            run_id=_decode_text(fields["run_id"]),
            tenant_id=_decode_text(fields["tenant_id"]),
            sequence=int(_decode_text(fields["sequence"])),
            occurred_at_epoch_ms=int(_decode_text(fields["occurred_at_epoch_ms"])),
            status=RunStatus(_decode_text(fields["status"])),
            payload=payload_value,
        )
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("REDIS_EVENT_FORMAT_INVALID") from error


class RedisRunEventStore:
    """把 S2 RunEventRecord 投递到带前缀和 TTL 的 Redis Stream。"""

    ttl_seconds = 900
    max_events = 20
    max_payload_bytes = 64 * 1024

    def __init__(
        self,
        client: Any,
        run_stamp: str,
        *,
        ttl_seconds: int = 900,
        max_events: int = 20,
        max_payload_bytes: int = 64 * 1024,
    ) -> None:
        if client is None:
            raise ValueError("Redis 客户端必须通过依赖注入提供")
        if not isinstance(run_stamp, str) or not _STAMP.fullmatch(run_stamp):
            raise ValueError("run_stamp 只能包含字母、数字、下划线或连字符")
        if ttl_seconds <= 0 or max_events <= 0 or max_payload_bytes <= 0:
            raise ValueError("TTL、事件上限和载荷上限必须为正数")
        self.client = client
        self.run_stamp = run_stamp
        self.ttl_seconds = ttl_seconds
        self.max_events = max_events
        self.max_payload_bytes = max_payload_bytes
        self.stream_key = f"s7:{run_stamp}:events"
        self._events: list[RunEventRecord] = []
        self._event_ids: dict[str, int] = {}
        self._event_records: dict[str, RunEventRecord] = {}

    async def append(self, event: RunEventRecord) -> bool:
        """追加事件；重复事件 ID 幂等返回 False，过期或乱序事件拒绝。"""
        if not isinstance(event, RunEventRecord):
            raise TypeError("event 必须是 RunEventRecord")
        await self._sync_external_cache()
        old_sequence = self._event_ids.get(event.event_id)
        if old_sequence is not None:
            if (
                old_sequence != event.sequence
                or self._event_records[event.event_id] != event
            ):
                raise ValueError("同一事件 ID 不得对应不同事件内容")
            return False
        if self._events and event.sequence <= self._events[-1].sequence:
            raise ValueError("事件 sequence 必须单调递增")
        payload = _plain(event.payload)
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(payload_json.encode("utf-8")) > self.max_payload_bytes:
            raise ValueError("事件 payload 超出大小上限")
        if len(self._events) >= self.max_events:
            raise ValueError("事件数量超出上限")
        fields = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "run_id": event.run_id,
            "tenant_id": event.tenant_id,
            "sequence": str(event.sequence),
            "occurred_at_epoch_ms": str(event.occurred_at_epoch_ms),
            "status": event.status.value,
            "payload": payload_json,
        }
        await _call(
            self.client,
            "xadd",
            self.stream_key,
            fields,
            maxlen=self.max_events,
            approximate=False,
        )
        await _call(self.client, "expire", self.stream_key, self.ttl_seconds)
        self._events.append(event)
        self._event_ids[event.event_id] = event.sequence
        self._event_records[event.event_id] = event
        return True

    async def list_after(
        self, run_id: str, tenant_id: str, after_sequence: int
    ) -> Sequence[RunEventRecord]:
        """按 S2 游标返回指定租户和 Run 的后续事件。"""
        if not isinstance(after_sequence, int) or after_sequence < 0:
            raise ValueError("after_sequence 必须是非负整数")
        external_events = await self._stream_events()
        source = self._events if external_events is None else external_events
        return tuple(
            event
            for event in source
            if event.run_id == run_id
            and event.tenant_id == tenant_id
            and event.sequence > after_sequence
        )

    async def list_after_event_id(
        self, run_id: str, tenant_id: str, last_event_id: str | None
    ) -> Sequence[RunEventRecord]:
        """按 Last-Event-ID 续读；未知 ID 从头返回当前短期窗口。"""
        external_events = await self._stream_events()
        source = self._events if external_events is None else external_events
        if last_event_id is None:
            return await self.list_after(run_id, tenant_id, 0)
        sequence = next(
            (
                event.sequence
                for event in source
                if event.event_id == last_event_id
                and event.run_id == run_id
                and event.tenant_id == tenant_id
            ),
            0,
        )
        return tuple(
            event
            for event in source
            if event.run_id == run_id
            and event.tenant_id == tenant_id
            and event.sequence > sequence
        )

    async def _stream_events(self) -> tuple[RunEventRecord, ...] | None:
        """从注入 Redis Stream 回读事件；无回读能力时使用离线缓存。"""

        if not callable(getattr(self.client, "xrange", None)):
            return None
        rows = await _call(
            self.client,
            "xrange",
            self.stream_key,
            min="-",
            max="+",
            count=self.max_events,
        )
        return tuple(_parse_stream_row(row) for row in (rows or ()))

    async def _sync_external_cache(self) -> None:
        """在新进程首次写入前同步已有 Stream 窗口，保持本地约束连续。"""

        if self._events:
            return
        external_events = await self._stream_events()
        if external_events is None:
            return
        self._events = list(external_events)
        self._event_ids = {event.event_id: event.sequence for event in self._events}
        self._event_records = {event.event_id: event for event in self._events}

    async def close(self) -> None:
        """关闭注入客户端；不存在关闭方法时保持无副作用。"""
        if getattr(self.client, "aclose", None) is not None:
            await _call(self.client, "aclose")
        else:
            await _call(self.client, "close")

    async def publish(self, event: RunEventRecord) -> bool:
        """兼容事件总线命名的追加入口。"""
        return await self.append(event)

    async def read_after(
        self, run_id: str, tenant_id: str, last_event_id: str | None = None
    ) -> Sequence[RunEventRecord]:
        """兼容 SSE 事件总线命名的续读入口。"""
        return await self.list_after_event_id(run_id, tenant_id, last_event_id)


RedisEventStore = RedisRunEventStore
RedisRunEventBus = RedisRunEventStore
RedisStreamEventStore = RedisRunEventStore

__all__ = [
    "RedisEventStore",
    "RedisRunEventBus",
    "RedisRunEventStore",
    "RedisStreamEventStore",
]
