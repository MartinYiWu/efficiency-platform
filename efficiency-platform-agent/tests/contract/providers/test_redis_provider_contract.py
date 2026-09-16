"""S7 Redis 与 Taskiq 适配边界的离线契约测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.core.run import JsonObject
from efficiency_platform_agent.core.runtime import RunEventRecord
from efficiency_platform_agent.providers.cache.redis import RedisRunEventStore
from efficiency_platform_agent.tasks.acceptance_probe import (
    AcceptanceProbeError,
    validate_synthetic_input,
)
from efficiency_platform_agent.tasks.broker import SingleWorkerTaskBroker


class _FakeRedis:
    """仅记录命令的 Redis 协议 Stub，不会建立网络连接。"""

    def __init__(self) -> None:
        self.streams: dict[str, list[dict[str, object]]] = {}
        self.stream_ids: dict[str, list[str]] = {}
        self.sets: dict[str, set[str]] = {}
        self.expirations: dict[str, int] = {}
        self.closed = False

    async def xadd(self, key: str, fields: dict[str, object], **kwargs: object) -> str:
        rows = self.streams.setdefault(key, [])
        rows.append(dict(fields))
        entry_id = f"{len(rows)}-0"
        self.stream_ids.setdefault(key, []).append(entry_id)
        return entry_id

    async def xrange(
        self, key: str, min: str = "-", max: str = "+", count: int | None = None
    ) -> list[tuple[str, dict[str, object]]]:
        del min, max
        rows = self.streams.get(key, [])
        ids = self.stream_ids.get(key, [])
        values = list(zip(ids, rows, strict=False))
        return values[:count] if count is not None else values

    async def expire(self, key: str, seconds: int) -> bool:
        self.expirations[key] = seconds
        return True

    async def sadd(self, key: str, value: str) -> int:
        values = self.sets.setdefault(key, set())
        before = len(values)
        values.add(value)
        return 1 if len(values) > before else 0

    async def sismember(self, key: str, value: str) -> bool:
        return value in self.sets.get(key, set())

    async def aclose(self) -> None:
        self.closed = True


class RedisProviderContractTests(unittest.IsolatedAsyncioTestCase):
    def _event(self, sequence: int, event_id: str | None = None) -> RunEventRecord:
        return RunEventRecord(
            event_id=event_id or f"evt-{sequence}",
            event_type="run_started",
            run_id="run-1",
            tenant_id="tenant-1",
            sequence=sequence,
            occurred_at_epoch_ms=sequence,
            status=RunStatus.RUNNING,
            payload=JsonObject(),
        )

    async def test_event_store_uses_prefix_ttl_monotonic_and_continuation(self) -> None:
        redis = _FakeRedis()
        store = RedisRunEventStore(redis, "stamp-1")
        await store.append(self._event(1))
        await store.append(self._event(2))
        duplicate = await store.append(self._event(2))
        self.assertFalse(duplicate)
        self.assertEqual(redis.expirations["s7:stamp-1:events"], 900)
        self.assertTrue(all(key.startswith("s7:stamp-1:") for key in redis.streams))
        events = await store.list_after("run-1", "tenant-1", 1)
        self.assertEqual([event.sequence for event in events], [2])
        with self.assertRaises(ValueError):
            await store.append(self._event(1, "evt-old"))
        await store.close()
        self.assertTrue(redis.closed)

    async def test_event_store_replays_events_from_stream_for_a_new_instance(
        self,
    ) -> None:
        redis = _FakeRedis()
        writer = RedisRunEventStore(redis, "stamp-1", max_events=2)
        await writer.append(self._event(1))
        await writer.append(self._event(2))

        reader = RedisRunEventStore(redis, "stamp-1", max_events=2)
        events = await reader.list_after("run-1", "tenant-1", 0)
        continued = await reader.list_after_event_id("run-1", "tenant-1", "evt-1")
        with self.assertRaises(ValueError):
            await reader.append(self._event(3))
        after_append = await reader.list_after("run-1", "tenant-1", 1)

        self.assertEqual([event.event_id for event in events], ["evt-1", "evt-2"])
        self.assertEqual([event.event_id for event in continued], ["evt-2"])
        self.assertEqual([event.event_id for event in after_append], ["evt-2"])

    async def test_broker_idempotency_cancellation_and_failure_normalization(
        self,
    ) -> None:
        broker = SingleWorkerTaskBroker(_FakeRedis(), "stamp-1")
        first = await broker.enqueue(
            "task-1", {"run_stamp": "stamp-1", "sequence": 1}, idempotency_key="same"
        )
        again = await broker.enqueue(
            "task-1", {"run_stamp": "stamp-1", "sequence": 1}, idempotency_key="same"
        )
        self.assertEqual(first, again)
        self.assertTrue(await broker.cancel("task-1"))
        self.assertTrue(await broker.is_cancelled("task-1"))
        self.assertEqual(
            broker.normalize_failure(RuntimeError("secret-url"))["code"], "TASK_FAILED"
        )

    async def test_broker_replays_idempotency_after_new_instance(self) -> None:
        redis = _FakeRedis()
        payload = {"run_stamp": "stamp-1", "sequence": 1}
        writer = SingleWorkerTaskBroker(redis, "stamp-1")
        await writer.enqueue("task-1", payload, idempotency_key="same")

        reader = SingleWorkerTaskBroker(redis, "stamp-1")
        with self.assertRaises(ValueError):
            await reader.enqueue(
                "task-2",
                {"run_stamp": "stamp-1", "sequence": 2},
                idempotency_key="same",
            )

    async def test_broker_replays_cancellation_after_new_instance(self) -> None:
        redis = _FakeRedis()
        writer = SingleWorkerTaskBroker(redis, "stamp-1")
        await writer.cancel("task-1")

        reader = SingleWorkerTaskBroker(redis, "stamp-1")

        self.assertTrue(await reader.is_cancelled("task-1"))

    async def test_event_count_and_payload_limits_are_enforced(self) -> None:
        redis = _FakeRedis()
        store = RedisRunEventStore(redis, "stamp-1", max_events=1, max_payload_bytes=8)
        await store.append(self._event(1))
        with self.assertRaises(ValueError):
            await store.append(self._event(2))
        limited = RedisRunEventStore(_FakeRedis(), "stamp-2", max_payload_bytes=4)
        with self.assertRaises(ValueError):
            await limited.append(
                RunEventRecord(
                    event_id="large",
                    event_type="run_started",
                    run_id="run-1",
                    tenant_id="tenant-1",
                    sequence=1,
                    occurred_at_epoch_ms=1,
                    status=RunStatus.RUNNING,
                    payload=JsonObject((("x", "超长"),)),
                )
            )

    def test_probe_rejects_untrusted_fields(self) -> None:
        self.assertEqual(
            validate_synthetic_input({"run_stamp": "s", "task_id": "t", "sequence": 1})[
                "task_id"
            ],
            "t",
        )
        with self.assertRaises(AcceptanceProbeError):
            validate_synthetic_input(
                {"run_stamp": "s", "task_id": "t", "sequence": 1, "user_text": "正文"}
            )


__all__ = ["RedisProviderContractTests"]
