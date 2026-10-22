"""独立智能客服 Graph 的严格运行态与输出契约。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import BlockKind, EvidenceMode


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IntentType(StrEnum):
    COMPANY_QUERY = "COMPANY_QUERY"
    GENERAL_QUERY = "GENERAL_QUERY"
    MIXED_QUERY = "MIXED_QUERY"
    AMBIGUOUS_QUERY = "AMBIGUOUS_QUERY"


class AnswerMode(StrEnum):
    COMPANY_KNOWLEDGE = "COMPANY_KNOWLEDGE"
    MIXED = "MIXED"
    GENERAL_ADVICE = "GENERAL_ADVICE"
    CLARIFY = "CLARIFY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class HistoryMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class CustomerServiceRunRequest(StrictModel):
    contract_version: Literal["customer-service-run/1"]
    request_id: str = Field(min_length=1, max_length=128)
    conversation_id: UUID
    tenant_id: str = Field(min_length=1, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)
    agent_release_id: UUID
    message: str = Field(min_length=1, max_length=12000)
    history: tuple[HistoryMessage, ...] = Field(max_length=12)

    @model_validator(mode="after")
    def validate_history_size(self) -> CustomerServiceRunRequest:
        if sum(len(item.content) for item in self.history) > 12000:
            raise ValueError("history 总字符数不得超过 12000")
        return self


class IntentDecision(StrictModel):
    intent_type: IntentType
    requires_company_knowledge: bool
    requires_general_advice: bool
    missing_field: str | None = None
    normalized_question: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_ambiguity(self) -> IntentDecision:
        if self.intent_type is IntentType.AMBIGUOUS_QUERY and not self.missing_field:
            raise ValueError("AMBIGUOUS_QUERY 必须给出一个 missing_field")
        if self.intent_type is not IntentType.AMBIGUOUS_QUERY and self.missing_field:
            raise ValueError("非歧义意图不得给出 missing_field")
        return self


class QueryRewrite(StrictModel):
    queries: tuple[str, ...] = Field(min_length=1, max_length=10)


class Evidence(StrictModel):
    chunk_id: UUID
    parent_id: UUID | None = None
    knowledge_base_id: UUID
    document_id: UUID
    document_version_id: UUID
    index_release_id: UUID
    document_title: str = Field(min_length=1)
    version_no: int = Field(gt=0)
    section_path: str | None = None
    page_no: int | None = Field(default=None, gt=0)
    content: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    hit_content: str | None = None
    hit_content_hash: str | None = None
    hit_start_offset: int | None = None
    hit_end_offset: int | None = None
    score: float


class ParentEvidence(StrictModel):
    block_kind: BlockKind = "LIST"
    evidence_mode: EvidenceMode = "FULL_ONLY"
    parent_id: UUID
    knowledge_base_id: UUID
    document_id: UUID
    document_version_id: UUID
    index_release_id: UUID
    document_title: str = Field(min_length=1)
    version_no: int = Field(gt=0)
    section_path: str | None = None
    page_no: int | None = Field(default=None, gt=0)
    page_end: int | None = Field(default=None, gt=0)
    content: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    token_count: int = Field(gt=0)


class SupportedClaim(StrictModel):
    claim: str = Field(min_length=1)
    supporting_chunk_ids: tuple[UUID, ...] = Field(min_length=1)


class SufficiencyDecision(StrictModel):
    sufficient: bool
    supported_claims: tuple[SupportedClaim, ...]
    unsupported_claims: tuple[str, ...]
    conflicts: tuple[str, ...]
    recommended_mode: AnswerMode

    @model_validator(mode="before")
    @classmethod
    def reject_false_sufficiency(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("conflicts"):
            return value | {
                "sufficient": False,
                "recommended_mode": AnswerMode.INSUFFICIENT_EVIDENCE,
            }
        return value


class CompanyParagraph(StrictModel):
    text: str = Field(min_length=1)
    supporting_chunk_ids: tuple[UUID, ...] = Field(min_length=1)


class CompanySection(StrictModel):
    title: str = Field(min_length=1)
    paragraphs: tuple[CompanyParagraph, ...] = Field(min_length=1)


class GeneralAdvice(StrictModel):
    title: Literal["通用建议，非公司制度"] = "通用建议，非公司制度"
    paragraphs: tuple[str, ...] = Field(min_length=1)


class CustomerServiceAnswer(StrictModel):
    contract_version: Literal["customer-service-answer/1"]
    answer_mode: AnswerMode
    company_sections: tuple[CompanySection, ...] = ()
    general_advice: GeneralAdvice | None = None
    clarification_question: str | None = None
    insufficiency_reason: str | None = None

    @model_validator(mode="after")
    def validate_mode_shape(self) -> CustomerServiceAnswer:
        if self.answer_mode is AnswerMode.COMPANY_KNOWLEDGE:
            if not self.company_sections or self.general_advice is not None:
                raise ValueError("公司知识回答区块无效")
        elif self.answer_mode is AnswerMode.MIXED:
            if not self.company_sections or self.general_advice is None:
                raise ValueError("混合回答区块无效")
        elif self.answer_mode is AnswerMode.GENERAL_ADVICE:
            if self.company_sections or self.general_advice is None:
                raise ValueError("通用建议回答区块无效")
        elif self.answer_mode is AnswerMode.CLARIFY:
            if (
                self.company_sections
                or self.general_advice
                or not self.clarification_question
            ):
                raise ValueError("澄清回答必须且只能包含一个问题")
        elif self.answer_mode is AnswerMode.INSUFFICIENT_EVIDENCE and (
            self.company_sections
            or self.general_advice
            or not self.insufficiency_reason
        ):
            raise ValueError("证据不足回答区块无效")
        return self


class Citation(StrictModel):
    citation_no: int = Field(gt=0)
    knowledge_base_id: UUID
    document_id: UUID
    document_version_id: UUID
    index_release_id: UUID
    chunk_id: UUID
    document_title: str
    version_no: int = Field(gt=0)
    section_path: str | None
    page_no: int | None
    quoted_text: str
    content_hash: str


class RenderedAnswer(StrictModel):
    answer: CustomerServiceAnswer
    markdown: str
    citations: tuple[Citation, ...]


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class RunView(StrictModel):
    contract_version: Literal["customer-service-run-view/1"] = (
        "customer-service-run-view/1"
    )
    run_id: UUID
    request_id: str
    status: RunStatus


class RunEventPayload(StrictModel):
    stage: str | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    public_summary: str | None = None
    delta: str | None = None
    answer_mode: AnswerMode | None = None
    citation: Citation | None = None
    error_code: str | None = None
    error_message: str | None = None
    retrieval_facts: dict[str, Any] | None = None


class RunEvent(StrictModel):
    contract_version: Literal["customer-service-run-event/1"] = (
        "customer-service-run-event/1"
    )
    run_id: UUID
    sequence: int = Field(gt=0)
    event_type: str = Field(min_length=1)
    status: RunStatus
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: RunEventPayload


class DebugKnowledgeBinding(StrictModel):
    knowledge_base_id: UUID
    index_release_id: UUID


class DebugRequest(StrictModel):
    contract_version: Literal["customer-service-rag-debug/1"]
    agent_key: Literal["customer-service"]
    tenant_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1)
    agent_release_id: UUID
    agent_version_id: UUID
    rag_policy_version_id: UUID
    knowledge_bindings: tuple[DebugKnowledgeBinding, ...] = Field(min_length=1)


__all__ = [name for name in globals() if not name.startswith("_")]
