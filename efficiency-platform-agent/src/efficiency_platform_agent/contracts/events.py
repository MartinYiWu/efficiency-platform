"""SSE 使用的版本化运行事件契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from efficiency_platform_agent.core.enums import RunStatus

type JsonValue = str | int | float | bool | None | list[object] | dict[str, object]
EventType = Literal[
    "run_created",
    "run_queued",
    "run_started",
    "strategy_selected",
    "context_built",
    "prompt_rendered",
    "tool_started",
    "tool_completed",
    "model_selected",
    "model_degraded",
    "model_completed",
    "checkpoint_saved",
    "budget_exhausted",
    "strategy_event",
    "run_waiting_input",
    "run_resumed",
    "run_cancel_requested",
    "run_cancelled",
    "run_timed_out",
    "run_succeeded",
    "run_failed",
]


class RunEventV1(BaseModel):
    """可通过 SSE 输出的最小运行事件。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["run.event/1"] = "run.event/1"
    event_id: str
    event_type: EventType
    run_id: str
    sequence: int = Field(ge=1)
    occurred_at_epoch_ms: int = Field(ge=1)
    status: RunStatus
    payload: dict[str, JsonValue] = Field(default_factory=dict)


__all__ = ["EventType", "JsonValue", "RunEventV1"]
