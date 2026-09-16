"""S7 Redis/Taskiq 组合的离线集成测试，不连接真实服务。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.core.run import JsonObject
from efficiency_platform_agent.core.runtime import RunEventRecord
from efficiency_platform_agent.providers.cache.redis import RedisRunEventStore
from efficiency_platform_agent.tasks.broker import SingleWorkerTaskBroker


class _ProtocolRedis:
    """记录 Stream 命令的最小协议 Fake。"""

    def __init__(self) -> None:
        self.commands: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.closed = False

    async def xadd(self, *args: object, **kwargs: object) -> str:
        self.commands.append(("xadd", args, kwargs))
        return "1-0"

    async def expire(self, *args: object, **kwargs: object) -> bool:
        self.commands.append(("expire", args, kwargs))
        return True

    async def aclose(self) -> None:
        self.closed = True


class RedisTaskiqOfflineTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_and_broker_share_stamp_but_keep_key_spaces(self) -> None:
        client = _ProtocolRedis()
        event_store = RedisRunEventStore(client, "offline")
        broker = SingleWorkerTaskBroker(client, "offline")
        event = RunEventRecord(
            event_id="e1",
            event_type="run_started",
            run_id="r1",
            tenant_id="t1",
            sequence=1,
            occurred_at_epoch_ms=1,
            status=RunStatus.RUNNING,
            payload=JsonObject(),
        )
        await event_store.append(event)
        await broker.enqueue("task-1", {"run_stamp": "offline", "sequence": 1})
        keys = [
            str(command[1][0]) for command in client.commands if command[0] == "xadd"
        ]
        self.assertEqual(keys, ["s7:offline:events", "s7:offline:tasks"])
        expirations = [
            command[1] for command in client.commands if command[0] == "expire"
        ]
        self.assertEqual(
            expirations,
            [("s7:offline:events", 900), ("s7:offline:tasks", 900)],
        )

    async def test_max_messages_and_shutdown_are_local(self) -> None:
        client = _ProtocolRedis()
        broker = SingleWorkerTaskBroker(client, "offline", max_messages=1)
        await broker.enqueue("task-1", {"run_stamp": "offline", "sequence": 1})
        with self.assertRaises(ValueError):
            await broker.enqueue("task-2", {"run_stamp": "offline", "sequence": 2})
        await broker.close()
        self.assertTrue(client.closed)


__all__ = ["RedisTaskiqOfflineTests"]
