"""运营助手流式输出使用的版本化事件契约。"""

from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from efficiency_platform_agent.core.operation_progress import OperationVisiblePhase


def _validated_json(value: Any) -> Any:
    """递归校验并隔离快照，拒绝非 JSON 类型。"""

    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and not isfinite(value):
            raise ValueError("JSON 数值不能是 NaN 或无穷大")
        return value
    if isinstance(value, list):
        return [_validated_json(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("JSON 对象键必须是字符串")
        return {key: _validated_json(item) for key, item in value.items()}
    raise ValueError("值必须是严格 JSON 类型")


JsonValue = Annotated[
    Any, BeforeValidator(lambda value: deepcopy(_validated_json(value)))
]
StreamEventName = Literal[
    "run_started",
    "intent_detected",
    "clarification_required",
    "phase_started",
    "research_started",
    "research_completed",
    "content_generation_started",
    "content_generation_completed",
    "quality_checked",
    "assistant_started",
    "assistant_delta",
    "deliverable",
    "usage_update",
    "stream_error",
    "stream_done",
]
_OPERATION_VISIBLE_PHASES = frozenset(get_args(OperationVisiblePhase))


class RunStreamEventV1(BaseModel):
    """可回放、可去重的对话流事件。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["run.stream.event/1"] = Field(
        default="run.stream.event/1", description="流事件契约版本。"
    )
    event: StreamEventName = Field(description="受控流事件名称。")
    run_id: str = Field(min_length=1, max_length=128, description="Run 标识。")
    sequence: int = Field(ge=1, description="Run 内单调递增的事件序号。")
    payload: dict[str, JsonValue] = Field(
        default_factory=dict, description="脱敏后的严格 JSON 事件数据。"
    )

    @model_validator(mode="after")
    def validate_visible_phase(self) -> RunStreamEventV1:
        """禁止事件载荷透传内部阶段，并约束可选进度计数。"""

        progress: dict[str, int] = {}
        for key in ("completed", "target"):
            value = self.payload.get(key)
            if value is None:
                continue
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{key} 必须是非负整数")
            progress[key] = value
        if (
            "completed" in progress
            and "target" in progress
            and progress["completed"] > progress["target"]
        ):
            raise ValueError("completed 不得大于 target")
        phase = self.payload.get("phase")
        if phase is None:
            if self.event == "phase_started":
                raise ValueError("phase_started 必须包含 phase")
            return self
        if not isinstance(phase, str) or phase not in _OPERATION_VISIBLE_PHASES:
            raise ValueError("运营阶段必须是用户可见阶段")
        return self


__all__ = [
    "JsonValue",
    "OperationVisiblePhase",
    "RunStreamEventV1",
    "StreamEventName",
]
