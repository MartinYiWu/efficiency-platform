"""本地研究事实的中立身份和类型化快照，不持有执行器或正文日志。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .research_evidence_v2 import (
    ClaimRecordV2,
    EventClusterV2,
    EvidenceRefV2,
    SourceDocumentV2,
)
from .research_sources_v2 import CandidateRecordV2, ExtractedDocumentV2, SourceAttemptV2
from .research_v2 import (
    CollectionPlanV2,
    DeliveryDraftV2,
    DeliveryPackV2,
    OutputDecisionV2,
    QualityReportV2,
    ResearchBriefV2,
    ResearchOutcomeV2,
)


class LocalResearchRunKeyV2(BaseModel):
    """所有字段必须由可信会话和 Run 上下文提供。"""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    tenant_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=1, strict=True)


class LocalResearchResourceCountsV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    http_requests: int = Field(default=0, ge=0, le=60)
    body_requests: int = Field(default=0, ge=0, le=30)
    model_calls: int = Field(default=0, ge=0)
    downloaded_bytes: int = Field(default=0, ge=0)


class LocalResearchRunFactsV2(BaseModel):
    """映射值全部复用正式 V2 契约；每次写入都重新校验。"""

    model_config = ConfigDict(extra="forbid", frozen=True)
    key: LocalResearchRunKeyV2
    brief: ResearchBriefV2
    version: int = Field(default=0, ge=0, strict=True)
    created_at: datetime
    expires_at: datetime
    status: Literal["active", "completed", "failed", "cancelled", "timed_out"] = (
        "active"
    )
    candidates: dict[str, CandidateRecordV2] = Field(default_factory=dict)
    extracted_documents: dict[str, ExtractedDocumentV2] = Field(default_factory=dict)
    documents: dict[str, SourceDocumentV2] = Field(default_factory=dict)
    events: dict[str, EventClusterV2] = Field(default_factory=dict)
    claims: dict[str, ClaimRecordV2] = Field(default_factory=dict)
    evidence: dict[str, EvidenceRefV2] = Field(default_factory=dict)
    quality_reports: dict[str, QualityReportV2] = Field(default_factory=dict)
    deliveries: dict[str, DeliveryPackV2] = Field(default_factory=dict)
    plans: dict[str, CollectionPlanV2] = Field(default_factory=dict)
    attempts: dict[str, SourceAttemptV2] = Field(default_factory=dict)
    drafts: dict[str, DeliveryDraftV2] = Field(default_factory=dict)
    output_decisions: dict[str, OutputDecisionV2] = Field(default_factory=dict)
    stage_artifact_ids: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    resources: LocalResearchResourceCountsV2 = Field(
        default_factory=LocalResearchResourceCountsV2
    )
    outcome: ResearchOutcomeV2 | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> LocalResearchRunFactsV2:
        trusted = self.brief.trusted_context
        if (
            self.key.tenant_id,
            self.key.run_id,
            self.key.task_id,
            self.key.revision,
        ) != (
            trusted.tenant_id,
            trusted.run_id,
            trusted.task_id,
            self.brief.intent_revision,
        ):
            raise ValueError("LOCAL_RESEARCH_IDENTITY_MISMATCH")
        if any(
            item.tzinfo is None or item.utcoffset() is None
            for item in (self.created_at, self.expires_at)
        ):
            raise ValueError("LOCAL_RESEARCH_TIME_NAIVE")
        if self.expires_at <= self.created_at:
            raise ValueError("LOCAL_RESEARCH_TTL_INVALID")
        return self
