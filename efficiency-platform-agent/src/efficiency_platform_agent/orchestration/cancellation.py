"""可唤醒且幂等的进程内取消信号。"""

from __future__ import annotations

import asyncio


class InMemoryCancellationSignal:
    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    async def _event(self, run_id: str) -> asyncio.Event:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be non-empty")
        async with self._lock:
            return self._events.setdefault(run_id, asyncio.Event())

    async def request(self, run_id: str) -> None:
        (await self._event(run_id)).set()

    async def is_requested(self, run_id: str) -> bool:
        return (await self._event(run_id)).is_set()

    async def wait_requested(self, run_id: str) -> None:
        await (await self._event(run_id)).wait()
