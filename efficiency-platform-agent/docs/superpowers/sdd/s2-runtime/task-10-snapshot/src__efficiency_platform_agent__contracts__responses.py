"""Run API 对外暴露的最小安全响应契约。"""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from efficiency_platform_agent.core.enums import RunStatus, StrategyMode

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class RunErrorV1(BaseModel):
    """不泄露内部细节的稳定错误。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    category: str
    retryable: bool
    safe_message: str


class UsageV1(BaseModel):
    """一次 Run 的可信用量视图。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_microunits: int = Field(ge=0)
    estimated: bool


class CheckpointViewV1(BaseModel):
    """对外公开的 Checkpoint 标识。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    thread_id: str
    checkpoint_ns: str
    checkpoint_id: str


class RunViewV1(BaseModel):
    """Run 的安全公开视图。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["run.view/1"] = "run.view/1"
    run_id: str
    request_id: str
    status: RunStatus
    strategy: StrategyMode | None
    output: JsonValue = None
    error: RunErrorV1 | None = None
    usage: UsageV1
    checkpoint: CheckpointViewV1 | None = None
    degraded: bool = False
    last_event_id: str | None = None


__all__ = [
    "CheckpointViewV1",
    "JsonValue",
    "RunErrorV1",
    "RunViewV1",
    "UsageV1",
]
