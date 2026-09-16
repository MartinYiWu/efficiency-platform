"""Supervisor 事件的版本化、可序列化契约。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SupervisorEventType(StrEnum):
    STRATEGY_EVENT = "strategy_event"
    RUN_STARTED = "run_started"
    PLAN_BUILT = "plan_built"
    WAVE_SCHEDULED = "wave_scheduled"
    TASK_COMPLETED = "task_completed"
    WAITING_INPUT = "waiting_input"
    RUN_RESUMED = "run_resumed"
    RUN_CANCELLED = "run_cancelled"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


class SupervisorEventV1(BaseModel):
    """事件只含状态变更意图，不直接写入事件存储。"""

    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: Literal["supervisor-event/1"] = "supervisor-event/1"
    event_type: SupervisorEventType
    run_id: str
    sequence: int = Field(default=0, ge=0)
    attempt: int = Field(default=0, ge=0)
    revision: int = Field(default=0, ge=0)
    fence_token: int = Field(default=0, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    usage_delta: dict[str, int] = Field(default_factory=dict)

    def to_strategy_event(self) -> dict[str, object]:
        """转换为 S2 strategy_event 事实。"""

        return {
            "event_type": "strategy_event",
            "payload": {"event": self.event_type.value, **self.payload},
            "usage_delta": dict(self.usage_delta),
            "sequence": self.sequence,
            "attempt": self.attempt,
            "revision": self.revision,
            "fence_token": self.fence_token,
        }


__all__ = ["SupervisorEventType", "SupervisorEventV1"]
