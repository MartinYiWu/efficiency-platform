"""分段摘要的独立边界合同；不构成Java授权、CAS或模型质量证明。"""

from __future__ import annotations

from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.contracts.memory import (
    ConversationScopeModel,
    SourceDependencyModel,
)

Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
BoundedText = Annotated[str, Field(min_length=1, max_length=2048, pattern=r"\S")]
ContentOrigin = Literal[
    "USER_REQUIREMENT", "BUSINESS_FACT", "MODEL_SUGGESTION", "UNCONFIRMED_INFERENCE"
]
DecisionStatus = Literal["PROPOSED", "CONFIRMED", "REJECTED", "UNRESOLVED"]
DeriveMode = Literal["SUMMARY", "PROPOSALS", "BOTH"]
SourcePurpose = Literal["SUMMARY", "PROPOSALS"]
CandidateStatus = Literal["PENDING", "STALE"]


class _Boundary(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )


class CriticalValue(_Boundary):
    field_ref: Identifier
    kind: Literal["NUMBER", "DATE", "CONSTRAINT"]
    value: BoundedText = Field(repr=False)
    timezone: Identifier | None = None

    @model_validator(mode="after")
    def validate_timezone(self) -> Self:
        if self.kind == "DATE":
            if self.timezone is None:
                raise ValueError("SUMMARY_DATE_TIMEZONE_REQUIRED")
            try:
                ZoneInfo(self.timezone)
            except (ValueError, ZoneInfoNotFoundError):
                raise ValueError("SUMMARY_DATE_TIMEZONE_INVALID") from None
        elif self.timezone is not None:
            raise ValueError("SUMMARY_DATE_TIMEZONE_INVALID")
        return self


class SummaryEntry(_Boundary):
    claim_ref: Identifier
    text: BoundedText = Field(repr=False)
    content_origin: ContentOrigin
    decision_status: DecisionStatus
    source_refs: tuple[SourceDependencyModel, ...] = Field(min_length=1, max_length=128)
    basis_event_ref: SourceDependencyModel | None
    critical_values: tuple[CriticalValue, ...] = Field(
        default=(), max_length=128, repr=False
    )


class RejectedOption(SummaryEntry):
    reason: BoundedText | None = Field(repr=False)


class SummaryBasisEvent(_Boundary):
    """只允许可信Java/用户事件投影注入，模型输出不得构造确认权威。"""

    event_ref: SourceDependencyModel
    claim_ref: Identifier
    authority: Literal["USER", "JAVA", "MODEL"]
    content_origin: ContentOrigin
    decision_status: DecisionStatus
    critical_values: tuple[CriticalValue, ...] = Field(
        default=(), max_length=128, repr=False
    )
    rejection_reason: BoundedText | None = Field(default=None, repr=False)


class SummaryInputSource(_Boundary):
    """可信来源清单；无原文槽，不接收模型返回的权限和组完整性声明。"""

    source_ref: SourceDependencyModel
    scope: ConversationScopeModel
    sequence: int = Field(ge=0)
    group_id: Identifier
    group_members: tuple[SourceDependencyModel, ...] = Field(
        min_length=1, max_length=128
    )
    source_dependencies: tuple[SourceDependencyModel, ...] = Field(
        min_length=1, max_length=512
    )
    completed: bool
    source_kind: Literal["ORIGINAL", "SUMMARY"]
    allowed_purposes: frozenset[SourcePurpose]
    summary_scope_ref: Identifier | None
    proposals_scope_ref: Identifier | None
    summary_retention_ref: Identifier | None
    proposals_retention_ref: Identifier | None
    expires_at: int = Field(ge=0)
    critical_values: tuple[CriticalValue, ...] = Field(
        default=(), max_length=128, repr=False
    )


class SummaryWatermark(_Boundary):
    source_revision: int = Field(ge=0)
    first_sequence: int = Field(ge=0)
    last_sequence: int = Field(ge=0)


class SummarySegment(_Boundary):
    segment_id: Identifier
    scope: ConversationScopeModel
    covered_sources: tuple[SourceDependencyModel, ...] = Field(
        min_length=1, max_length=128
    )
    watermark: SummaryWatermark
    goal: SummaryEntry
    confirmed_constraints: tuple[SummaryEntry, ...] = Field(max_length=128, repr=False)
    decisions: tuple[SummaryEntry, ...] = Field(max_length=128, repr=False)
    rejected_options: tuple[RejectedOption, ...] = Field(max_length=128, repr=False)
    open_questions: tuple[SummaryEntry, ...] = Field(max_length=128, repr=False)
    important_refs: tuple[SummaryEntry, ...] = Field(max_length=128, repr=False)
    uncertainties: tuple[SummaryEntry, ...] = Field(max_length=128, repr=False)
    source_dependencies: tuple[SourceDependencyModel, ...] = Field(
        min_length=0, max_length=512
    )
    expires_at: int = Field(ge=0)
