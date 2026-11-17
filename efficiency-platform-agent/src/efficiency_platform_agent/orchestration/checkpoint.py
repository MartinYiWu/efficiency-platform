"""围绕 LangGraph saver 的进程内 Checkpoint 索引。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from efficiency_platform_agent.core.checkpoint_erasure import (
    CheckpointResidue,
    ThreadErasurePlan,
)
from efficiency_platform_agent.core.run import JsonObject

from .contracts import CheckpointView


@dataclass
class CheckpointRecord:
    view: CheckpointView
    state: dict


class InMemoryCheckpointStore:
    backend_id = "owned-memory"

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], CheckpointRecord] = {}

    def save(
        self,
        run_id: str,
        checkpoint_ns: str,
        state: dict,
        *,
        tenant_id: str = "",
        resume_binding=None,
        checkpoint_id: str | None = None,
    ) -> CheckpointView:
        cid = checkpoint_id or str(uuid.uuid4())
        view = CheckpointView(
            run_id, checkpoint_ns, cid, resume_binding or JsonObject()
        )
        self._records[(tenant_id, run_id, checkpoint_ns)] = CheckpointRecord(
            view, dict(state)
        )
        return view

    def get(
        self, run_id: str, checkpoint_ns: str, tenant_id: str = ""
    ) -> CheckpointRecord | None:
        return self._records.get((tenant_id, run_id, checkpoint_ns))

    async def delete_thread(
        self,
        thread_id: str,
        tenant_id: str,
        *,
        authorization: ThreadErasurePlan | None = None,
    ) -> None:
        keys = tuple(key for key in self._records if key[:2] == (tenant_id, thread_id))
        for key in keys:
            del self._records[key]

    async def remaining(
        self,
        thread_id: str,
        tenant_id: str,
        *,
        authorization: ThreadErasurePlan | None = None,
    ) -> CheckpointResidue:
        count = sum(key[:2] == (tenant_id, thread_id) for key in self._records)
        return CheckpointResidue(count, 0, 0)
