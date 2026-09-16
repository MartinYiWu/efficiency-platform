"""Run API 使用的版本化入站请求契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from efficiency_platform_agent.core.enums import StrategyMode

type JsonValue = str | int | float | bool | None | list[object] | dict[str, object]


class CreateRunRequestV1(BaseModel):
    """创建 Run 的受治理入站契约。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["run.create/1"] = "run.create/1"
    request_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    input_text: str = Field(min_length=1, max_length=20_000)
    requested_strategy: StrategyMode | None = None
    workflow_id: str | None = Field(default=None, min_length=1, max_length=128)
    strategy_payload_schema_version: str = Field(
        default="strategy.none/1", min_length=1, max_length=128
    )
    strategy_payload: dict[str, JsonValue] = Field(default_factory=dict)


class ResumeRunRequestV1(BaseModel):
    """使用原 Run 和 Checkpoint 恢复执行的契约。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["run.resume/1"] = "run.resume/1"
    tenant_id: str = Field(min_length=1, max_length=128)
    checkpoint_id: str = Field(min_length=1, max_length=256)
    resume_value: dict[str, JsonValue]


class CancelRunRequestV1(BaseModel):
    """请求协作取消同一 Run 的契约。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["run.cancel/1"] = "run.cancel/1"
    tenant_id: str = Field(min_length=1, max_length=128)
    reason_code: Literal["user_requested"] = "user_requested"


class RunQueryV1(BaseModel):
    """查询 Run 时使用的租户身份契约。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(min_length=1, max_length=128)


__all__ = [
    "CancelRunRequestV1",
    "CreateRunRequestV1",
    "JsonValue",
    "ResumeRunRequestV1",
    "RunQueryV1",
]
