"""自然语言意图解析使用的结构化契约。"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

IntentRequirementText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class IntentRequirementsV1(BaseModel):
    """八个运营 Manifest 所需条件的封闭、版本化输入。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["intent.requirements/1"] = "intent.requirements/1"
    topic: IntentRequirementText | None = None
    time_window: IntentRequirementText | None = None
    platforms: tuple[IntentRequirementText, ...] = Field(default=(), max_length=16)
    brand: IntentRequirementText | None = None
    product: IntentRequirementText | None = None
    goal: IntentRequirementText | None = None
    planning_window: IntentRequirementText | None = None
    ip: IntentRequirementText | None = None
    audience: IntentRequirementText | None = None
    incubation_window: IntentRequirementText | None = None
    campaign_goal: IntentRequirementText | None = None
    campaign_window: IntentRequirementText | None = None
    topic_scope: IntentRequirementText | None = None
    calendar_window: IntentRequirementText | None = None
    growth_goal: IntentRequirementText | None = None
    funnel_stage: IntentRequirementText | None = None
    experiment_window: IntentRequirementText | None = None
    review_window: IntentRequirementText | None = None
    metric_definition: IntentRequirementText | None = None


class IntentEnvelopeV1(BaseModel):
    """由模型解析并经 Agent 校验后的运营意图。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["intent/1"] = Field(
        default="intent/1", description="意图契约版本。"
    )
    domain: str = Field(min_length=1, max_length=128, description="业务领域。")
    goal: str = Field(min_length=1, max_length=2_000, description="用户目标。")
    task_type: str = Field(min_length=1, max_length=128, description="受控任务类型。")
    channels: list[str] = Field(default_factory=list, description="目标渠道或平台。")
    audience: str | None = Field(default=None, max_length=500, description="目标受众。")
    style: str | None = Field(default=None, max_length=500, description="内容风格。")
    time_range: str | None = Field(
        default=None, max_length=128, description="时间范围。"
    )
    needs_research: bool = Field(default=False, description="是否需要研究检索。")
    needs_multi_agent: bool = Field(
        default=False, description="是否需要多 Agent 编排。"
    )
    missing_fields: list[str] = Field(
        default_factory=list, description="缺失需求字段。"
    )
    needs_clarification: bool = Field(default=False, description="是否需要用户澄清。")
    confidence: float = Field(
        ge=0.0, le=1.0, description="意图解析置信度，范围为 0 到 1。"
    )
    model_hint: str | None = Field(
        default=None, max_length=128, description="模型等级建议。"
    )
    requirements: IntentRequirementsV1 = Field(
        default_factory=IntentRequirementsV1,
        description="Manifest 条件的受控输入；不得使用开放字典。",
    )


__all__ = ["IntentEnvelopeV1", "IntentRequirementsV1"]
