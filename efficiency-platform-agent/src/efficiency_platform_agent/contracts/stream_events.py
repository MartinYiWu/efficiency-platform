"""运营助手流式输出使用的版本化事件契约。"""

from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


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


__all__ = ["JsonValue", "RunStreamEventV1", "StreamEventName"]
