"""运营助手统一意图识别与任务规划契约。"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OperationScenario = Literal[
    "industry_digest",
    "multi_platform_content",
    "brand_operation_plan",
    "ip_operation_plan",
    "campaign_plan",
    "content_calendar",
    "growth_experiment",
    "operation_review",
]
ActionMode = Literal["create", "revise", "refresh", "clarify", "general_chat"]
NextStep = Literal["execute", "clarify", "answer"]
BoundedText = Annotated[str, Field(min_length=1, max_length=20_000)]


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IntentRequirementsV1(_FrozenContract):
    """模型从当前消息和可见历史提取的业务条件。"""

    topic: str | None = Field(default=None, max_length=2_000)
    platforms: tuple[str, ...] = Field(default=(), max_length=8)
    date_range: str | None = Field(default=None, max_length=256)
    target_audience: str | None = Field(default=None, max_length=2_000)
    brand: str | None = Field(default=None, max_length=1_000)
    product: str | None = Field(default=None, max_length=1_000)
    ip_name: str | None = Field(default=None, max_length=1_000)
    campaign_goal: str | None = Field(default=None, max_length=2_000)
    growth_goal: str | None = Field(default=None, max_length=2_000)
    funnel_stage: str | None = Field(default=None, max_length=256)
    metric_definition: str | None = Field(default=None, max_length=2_000)
    constraints: tuple[str, ...] = Field(default=(), max_length=32)


class ArtifactReferenceV1(_FrozenContract):
    """修改、刷新及序号指代所绑定的既有交付物。"""

    artifact_id: str | None = Field(default=None, max_length=128)
    version: int | None = Field(default=None, ge=1)
    referenced_item_index: int | None = Field(default=None, ge=1)
    reference_text: str | None = Field(default=None, max_length=1_000)

    @property
    def resolved(self) -> bool:
        return self.artifact_id is not None


class PlannedCapability(_FrozenContract):
    """规划器选择的受控能力，不允许模型直接提供 Prompt Key。"""

    capability_id: Literal[
        "research",
        "scenario_execute",
        "artifact_revise",
        "direct_answer",
    ]
    purpose: str = Field(min_length=1, max_length=1_000)
    depends_on: tuple[str, ...] = Field(default=(), max_length=8)


class IntentPlanV1(_FrozenContract):
    """每条用户消息进入运营助手后的第一份强类型决策。"""

    contract_version: Literal["intent-plan/1"] = "intent-plan/1"
    route_kind: Literal["operation", "general_chat"]
    primary_scenario: OperationScenario | None
    action_mode: ActionMode
    user_goal: BoundedText
    requirements: IntentRequirementsV1
    artifact_reference: ArtifactReferenceV1 = Field(
        default_factory=ArtifactReferenceV1
    )
    required_missing_fields: tuple[str, ...] = Field(default=(), max_length=16)
    next_step: NextStep
    clarification_question: str | None = Field(default=None, max_length=1_000)
    planned_capabilities: tuple[PlannedCapability, ...] = Field(
        default=(), max_length=8
    )
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_route_and_next_step(self) -> IntentPlanV1:
        if self.route_kind == "general_chat":
            if (
                self.primary_scenario is not None
                or self.action_mode != "general_chat"
                or self.next_step != "answer"
                or self.required_missing_fields
                or self.clarification_question is not None
                or self.planned_capabilities
            ):
                raise ValueError("GENERAL_CHAT_PLAN_INVALID")
            return self
        if self.primary_scenario is None or self.action_mode == "general_chat":
            raise ValueError("OPERATION_ROUTE_INVALID")
        if self.next_step == "clarify":
            if (
                not self.required_missing_fields
                or not self.clarification_question
                or self.planned_capabilities
            ):
                raise ValueError("CLARIFICATION_PLAN_INVALID")
            question_marks = self.clarification_question.count(
                "？"
            ) + self.clarification_question.count("?")
            if question_marks != 1:
                raise ValueError("CLARIFICATION_QUESTION_COUNT_INVALID")
            return self
        if self.required_missing_fields or self.clarification_question is not None:
            raise ValueError("NON_CLARIFICATION_FIELDS_INVALID")
        if self.next_step != "execute" or not self.planned_capabilities:
            raise ValueError("OPERATION_EXECUTION_PLAN_INVALID")
        if self.action_mode in {"revise", "refresh"} and not self.artifact_reference.resolved:
            raise ValueError("ARTIFACT_REFERENCE_REQUIRED")
        return self


__all__ = [
    "ActionMode",
    "ArtifactReferenceV1",
    "IntentPlanV1",
    "IntentRequirementsV1",
    "NextStep",
    "OperationScenario",
    "PlannedCapability",
]
