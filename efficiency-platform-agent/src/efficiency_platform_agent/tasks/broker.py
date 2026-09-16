"""Taskiq 单 Worker 的离线边界适配器。"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping, Sequence
from typing import Any


async def _call(client: Any, name: str, *args: Any, **kwargs: Any) -> Any:
    """调用注入客户端，兼容异步和同步 Fake。"""
    method = getattr(client, name, None)
    if method is None:
        return None
    result = method(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


class SingleWorkerTaskBroker:
    """用于单 Worker 验收的最小任务投递器，不启动真实 Worker。"""

    max_messages = 20
    max_payload_bytes = 64 * 1024
    ttl_seconds = 900

    def __init__(
        self,
        client: Any,
        run_stamp: str,
        *,
        max_messages: int = 20,
        max_payload_bytes: int = 64 * 1024,
        ttl_seconds: int = 900,
    ) -> None:
        if client is None or not run_stamp:
            raise ValueError("客户端和 run_stamp 必须由组合根提供")
        if max_messages <= 0 or max_payload_bytes <= 0 or ttl_seconds <= 0:
            raise ValueError("任务上限必须为正数")
        self.client = client
        self.run_stamp = run_stamp
        self.queue_key = f"s7:{run_stamp}:tasks"
        self.cancel_key = f"s7:{run_stamp}:cancelled"
        self.max_messages = max_messages
        self.max_payload_bytes = max_payload_bytes
        self.ttl_seconds = ttl_seconds
        self._messages: list[dict[str, Any]] = []
        self._idempotent: dict[str, str] = {}
        self._cancelled: set[str] = set()

    async def enqueue(
        self,
        task_id: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> str:
        """投递一次合成任务；相同幂等键不重复投递。"""
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id 不能为空")
        if not isinstance(payload, dict):
            raise TypeError("payload 必须是字典")
        if payload.get("run_stamp") != self.run_stamp:
            raise ValueError("任务 run_stamp 与 Broker 不一致")
        await self._sync_external_messages()
        if task_id in self._cancelled:
            raise ValueError("任务已取消")
        idem = idempotency_key or task_id
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > self.max_payload_bytes:
            raise ValueError("任务 payload 超出大小上限")
        if idem in self._idempotent:
            previous = next(
                item
                for item in self._messages
                if item["task_id"] == self._idempotent[idem]
            )
            previous_encoded = json.dumps(
                previous["payload"], ensure_ascii=False, separators=(",", ":")
            )
            if previous_encoded != encoded:
                raise ValueError("同一幂等键不得对应不同任务")
            return self._idempotent[idem]
        if len(self._messages) >= self.max_messages:
            raise ValueError("任务消息超出上限")
        await _call(
            self.client,
            "xadd",
            self.queue_key,
            {
                "task_id": task_id,
                "idempotency_key": idem,
                "payload": encoded,
            },
        )
        await _call(self.client, "expire", self.queue_key, self.ttl_seconds)
        self._messages.append({"task_id": task_id, "payload": payload})
        self._idempotent[idem] = task_id
        return task_id

    async def cancel(self, task_id: str) -> bool:
        """写入取消标记；重复取消幂等。"""
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id 不能为空")
        if task_id in self._cancelled:
            return False
        self._cancelled.add(task_id)
        await _call(self.client, "sadd", self.cancel_key, task_id)
        await _call(self.client, "expire", self.cancel_key, self.ttl_seconds)
        return True

    async def is_cancelled(self, task_id: str) -> bool:
        """检查协作式取消标记。"""
        if task_id in self._cancelled:
            return True
        external = await _call(self.client, "sismember", self.cancel_key, task_id)
        return bool(external)

    @staticmethod
    def normalize_failure(error: BaseException) -> dict[str, object]:
        """把异常归一化为不含内部正文的稳定错误。"""
        return {
            "code": "TASK_FAILED",
            "category": "task",
            "retryable": isinstance(error, (TimeoutError, ConnectionError)),
            "safe_message": "任务执行失败",
        }

    async def close(self) -> None:
        """关闭注入客户端，不启动或停止真实 Worker。"""
        if getattr(self.client, "aclose", None) is not None:
            await _call(self.client, "aclose")
        else:
            await _call(self.client, "close")

    async def submit(
        self,
        task_id: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> str:
        """兼容任务提交命名的入口。"""
        return await self.enqueue(task_id, payload, idempotency_key=idempotency_key)

    async def _sync_external_messages(self) -> None:
        """在新进程首次投递前恢复 Stream 中的幂等任务索引。"""

        if self._messages or not callable(getattr(self.client, "xrange", None)):
            return
        rows = await _call(
            self.client,
            "xrange",
            self.queue_key,
            min="-",
            max="+",
            count=self.max_messages,
        )
        for row in rows or ():
            if (
                not isinstance(row, Sequence)
                or isinstance(row, (str, bytes))
                or len(row) < 2
                or not isinstance(row[1], Mapping)
            ):
                raise ValueError("TASK_MESSAGE_FORMAT_INVALID")
            fields = row[1]
            task_id = self._decode_field(fields.get("task_id"))
            idempotency_key = self._decode_field(fields.get("idempotency_key"))
            encoded = self._decode_field(fields.get("payload"))
            try:
                payload = json.loads(encoded)
            except (TypeError, json.JSONDecodeError) as error:
                raise ValueError("TASK_MESSAGE_FORMAT_INVALID") from error
            if (
                not isinstance(payload, dict)
                or payload.get("run_stamp") != self.run_stamp
            ):
                raise ValueError("TASK_MESSAGE_FORMAT_INVALID")
            idem = idempotency_key or task_id
            if idem in self._idempotent:
                previous = next(
                    item
                    for item in self._messages
                    if item["task_id"] == self._idempotent[idem]
                )
                if previous["payload"] != payload:
                    raise ValueError("同一幂等键不得对应不同任务")
                continue
            self._messages.append({"task_id": task_id, "payload": payload})
            self._idempotent[idem] = task_id

    @staticmethod
    def _decode_field(value: object) -> str:
        """将 Redis 字段转换为非空文本。"""

        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("TASK_MESSAGE_FORMAT_INVALID")
        return value


TaskiqSingleWorkerBroker = SingleWorkerTaskBroker
TaskiqRedisBroker = SingleWorkerTaskBroker

__all__ = [
    "SingleWorkerTaskBroker",
    "TaskiqRedisBroker",
    "TaskiqSingleWorkerBroker",
]
