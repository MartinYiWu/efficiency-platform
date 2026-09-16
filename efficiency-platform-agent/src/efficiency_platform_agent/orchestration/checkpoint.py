"""围绕 LangGraph saver 的进程内 Checkpoint 索引。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from efficiency_platform_agent.core.run import JsonObject

from .contracts import CheckpointView


@dataclass
class CheckpointRecord:
    view: CheckpointView
    state: dict


class InMemoryCheckpointStore:
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
