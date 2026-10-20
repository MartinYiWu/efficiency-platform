"""摄取任务的进程内状态仓储；权威业务状态仍由 Java 保存。"""

from __future__ import annotations

import asyncio
from uuid import UUID

from .contracts import IngestJobView


class InMemoryIngestJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[UUID, IngestJobView] = {}
        self._lock = asyncio.Lock()

    async def create(self, view: IngestJobView) -> tuple[IngestJobView, bool]:
        async with self._lock:
            existing = self._jobs.get(view.task_id)
            if existing is not None:
                return existing, False
            self._jobs[view.task_id] = view
            return view, True

    async def get(self, task_id: UUID) -> IngestJobView | None:
        async with self._lock:
            return self._jobs.get(task_id)

    async def save(self, view: IngestJobView) -> None:
        async with self._lock:
            if view.task_id not in self._jobs:
                raise KeyError(view.task_id)
            self._jobs[view.task_id] = view


__all__ = ["InMemoryIngestJobRepository"]
