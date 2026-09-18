"""只消费已验证语义判别的确定性研究文档过滤。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.contracts.research_evidence_v2 import SourceDocumentV2
from efficiency_platform_agent.contracts.research_v2 import ResearchBriefV2

RELEVANCE_PROMPT_VERSION = "research.v2.relevance@1.0.0"


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticRelevanceDecisionV2(_FrozenContract):
    schema_version: Literal["semantic-relevance/2"] = "semantic-relevance/2"
    document_id: str = Field(min_length=1, max_length=128)
    document_content_hash: str = Field(min_length=16, max_length=128)
    brief_digest: str = Field(min_length=64, max_length=64)
    outcome: Literal["relevant", "irrelevant", "uncertain"]
    requirement_ids: tuple[str, ...] = Field(default=(), max_length=64)
    source_excerpt: str = Field(min_length=1, max_length=2_000)
    prompt_version: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_requirements(self) -> SemanticRelevanceDecisionV2:
        if len(set(self.requirement_ids)) != len(self.requirement_ids):
            raise ValueError("SEMANTIC_REQUIREMENT_DUPLICATED")
        return self


class DocumentFilterRecordV2(_FrozenContract):
    document_id: str = Field(min_length=1, max_length=128)
    stage: Literal["F0", "F1", "F2"]
    reason_code: str = Field(min_length=1, max_length=128)


class FilterResultV2(_FrozenContract):
    accepted_document_ids: tuple[str, ...] = Field(default=(), max_length=2_000)
    rejected: tuple[DocumentFilterRecordV2, ...] = Field(default=(), max_length=2_000)
    uncertain: tuple[DocumentFilterRecordV2, ...] = Field(default=(), max_length=2_000)
    input_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    uncertain_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_conservation(self) -> FilterResultV2:
        identifiers = list(self.accepted_document_ids) + [
            item.document_id for item in self.rejected + self.uncertain
        ]
        if (
            self.accepted_count != len(self.accepted_document_ids)
            or self.rejected_count != len(self.rejected)
            or self.uncertain_count != len(self.uncertain)
            or self.input_count != len(identifiers)
            or len(set(identifiers)) != len(identifiers)
        ):
            raise ValueError("FILTER_COUNT_CONSERVATION_INVALID")
        return self


def filter_documents(
    brief: ResearchBriefV2,
    documents: tuple[SourceDocumentV2, ...],
    semantic_decisions: tuple[SemanticRelevanceDecisionV2, ...],
) -> FilterResultV2:
    if not isinstance(brief, ResearchBriefV2):
        raise TypeError("brief 类型无效")
    document_ids = [item.document_id for item in documents]
    if len(set(document_ids)) != len(document_ids):
        raise ValueError("FILTER_DOCUMENT_DUPLICATED")
    decisions: dict[str, SemanticRelevanceDecisionV2] = {}
    for decision in semantic_decisions:
        if decision.document_id in decisions:
            raise ValueError("SEMANTIC_DECISION_DUPLICATED")
        decisions[decision.document_id] = decision
    if not set(decisions).issubset(document_ids):
        raise ValueError("SEMANTIC_DECISION_DOCUMENT_UNKNOWN")
    accepted: list[str] = []
    rejected: list[DocumentFilterRecordV2] = []
    uncertain: list[DocumentFilterRecordV2] = []
    for document in documents:
        disposition, stage, reason = _classify(
            brief,
            document,
            decisions.get(document.document_id),
        )
        if disposition == "accepted":
            accepted.append(document.document_id)
        else:
            record = DocumentFilterRecordV2(
                document_id=document.document_id,
                stage=stage,
                reason_code=reason,
            )
            (rejected if disposition == "rejected" else uncertain).append(record)
    return FilterResultV2(
        accepted_document_ids=tuple(accepted),
        rejected=tuple(rejected),
        uncertain=tuple(uncertain),
        input_count=len(documents),
        accepted_count=len(accepted),
        rejected_count=len(rejected),
        uncertain_count=len(uncertain),
    )


def _classify(
    brief: ResearchBriefV2,
    document: SourceDocumentV2,
    decision: SemanticRelevanceDecisionV2 | None,
) -> tuple[Literal["accepted", "rejected", "uncertain"], Literal["F0", "F1", "F2"], str]:
    if document.resource_status != "accepted":
        return "rejected", "F0", "RESOURCE_REJECTED"
    constraints = brief.source_constraints
    if document.source_id in constraints.excluded_source_ids:
        return "rejected", "F1", "SOURCE_EXCLUDED"
    if (
        constraints.allowed_source_ids is not None
        and document.source_id not in constraints.allowed_source_ids
    ):
        return "rejected", "F1", "SOURCE_NOT_ALLOWED"
    conditional = _conditional_constraints(brief, document)
    if conditional is not None:
        return conditional
    temporal = _temporal_disposition(brief, document)
    if temporal is not None:
        return temporal
    if decision is None:
        return "uncertain", "F2", "SEMANTIC_DECISION_MISSING"
    valid_requirements = {item.requirement_id for item in brief.hard_requirements}
    source_text = f"{document.title}\n{document.text}"
    if (
        decision.document_content_hash != document.content_hash
        or decision.brief_digest != brief.canonical_digest()
        or decision.prompt_version != RELEVANCE_PROMPT_VERSION
        or not set(decision.requirement_ids).issubset(valid_requirements)
        or (
            decision.outcome == "relevant"
            and bool(valid_requirements)
            and not decision.requirement_ids
        )
        or decision.source_excerpt not in source_text
    ):
        return "uncertain", "F2", "SEMANTIC_DECISION_STALE"
    if decision.outcome == "irrelevant":
        return "rejected", "F2", "SEMANTIC_IRRELEVANT"
    if decision.outcome == "uncertain":
        return "uncertain", "F2", "SEMANTIC_UNCERTAIN"
    return "accepted", "F2", "SEMANTIC_RELEVANT"


def _conditional_constraints(
    brief: ResearchBriefV2,
    document: SourceDocumentV2,
) -> tuple[Literal["rejected", "uncertain"], Literal["F1"], str] | None:
    constraints = brief.source_constraints
    if constraints.languages is not None:
        if document.language is None:
            return "uncertain", "F1", "LANGUAGE_UNKNOWN"
        if document.language not in constraints.languages:
            return "rejected", "F1", "LANGUAGE_MISMATCH"
    if constraints.event_regions is not None:
        if document.event_region is None:
            return "uncertain", "F1", "EVENT_REGION_UNKNOWN"
        if document.event_region not in constraints.event_regions:
            return "rejected", "F1", "EVENT_REGION_MISMATCH"
    if constraints.primary_only:
        if document.source_role == "unknown":
            return "uncertain", "F1", "SOURCE_ROLE_UNKNOWN"
        if document.source_role != "primary":
            return "rejected", "F1", "PRIMARY_SOURCE_REQUIRED"
    return None


def _temporal_disposition(
    brief: ResearchBriefV2,
    document: SourceDocumentV2,
) -> tuple[Literal["rejected", "uncertain"], Literal["F1"], str] | None:
    basis = brief.time_window.basis
    interval_end = None
    if basis == "published_at":
        timestamp = document.first_published_at or document.published_at
        if document.first_published_at is None:
            interval_end = document.published_interval_end
    elif basis == "updated_at":
        timestamp = document.updated_at
    else:
        timestamp = document.event_at
    if timestamp is None:
        return "uncertain", "F1", "TIME_UNKNOWN"
    window = brief.time_window
    if interval_end is None:
        if window.start <= timestamp < window.end:
            return None
        return "rejected", "F1", "TIME_OUTSIDE_WINDOW"
    if interval_end <= window.start or timestamp >= window.end:
        return "rejected", "F1", "TIME_OUTSIDE_WINDOW"
    if timestamp >= window.start and interval_end <= window.end:
        return None
    return "uncertain", "F1", "TIME_PARTIAL_OVERLAP"


__all__ = [
    "RELEVANCE_PROMPT_VERSION",
    "DocumentFilterRecordV2",
    "FilterResultV2",
    "SemanticRelevanceDecisionV2",
    "filter_documents",
]
