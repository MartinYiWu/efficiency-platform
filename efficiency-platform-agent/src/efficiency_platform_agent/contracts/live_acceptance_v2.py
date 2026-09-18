"""X04 服务器端真实验收的最小版本化契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

LIVE_ACCEPTANCE_CASE_PROMPTS: dict[str, str] = {
    "yesterday_ai": "收集昨天的 AI 行业动态并输出带来源摘要。",
    "last_week_topic": "收集上周大模型推理优化主题的公开动态并输出带来源摘要。",
    "exact_five": "收集昨天的 AI 行业动态，严格选 5 条；不足时明确说明。",
    "rewrite_wechat": "把刚才收集的几条动态改写成公众号文章，保留事实来源。",
    "ordinary_chat": "你好，你叫什么名字？",
}


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LiveAcceptanceRequestV1(_FrozenContract):
    contract_version: Literal["research-live-acceptance/1"] = (
        "research-live-acceptance/1"
    )
    request_id: str = Field(min_length=1, max_length=128)
    authorization_id: str = Field(min_length=1, max_length=128)
    case_ids: tuple[str, ...] = Field(min_length=1, max_length=5)
    requested_budget_microunits: int = Field(gt=0)

    @field_validator("case_ids")
    @classmethod
    def validate_case_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if (
            len(set(value)) != len(value)
            or any(case_id not in LIVE_ACCEPTANCE_CASE_PROMPTS for case_id in value)
        ):
            raise ValueError("LIVE_ACCEPTANCE_CASES_INVALID")
        return value


class LiveAcceptanceCaseResultV1(_FrozenContract):
    case_id: str = Field(min_length=1, max_length=64)
    status: Literal["PASS", "PARTIAL", "FAILED"]
    run_id: str | None = Field(default=None, min_length=1, max_length=128)
    real_model_verified: bool = False
    real_source_verified: bool = False


class LiveAcceptanceViewV1(_FrozenContract):
    contract_version: Literal["research-live-acceptance/1"] = (
        "research-live-acceptance/1"
    )
    request_id: str
    authorization_id: str
    acceptance_session_id: str
    status: Literal["PASS", "PARTIAL", "FAILED"]
    execution_mode: Literal["live"] = "live"
    external_io: bool
    approved_budget_microunits: int = Field(gt=0)
    used_cost_microunits: int = Field(ge=0)
    case_results: tuple[LiveAcceptanceCaseResultV1, ...] = ()
    reason_codes: tuple[str, ...] = ()


__all__ = [
    "LIVE_ACCEPTANCE_CASE_PROMPTS",
    "LiveAcceptanceCaseResultV1",
    "LiveAcceptanceRequestV1",
    "LiveAcceptanceViewV1",
]
