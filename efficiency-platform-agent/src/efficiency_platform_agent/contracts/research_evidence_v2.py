"""研究文档、事件、事实与证据的不可变契约。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceDocumentV2(_FrozenContract):
    schema_version: Literal["source-document/2"] = "source-document/2"
    document_id: str = Field(min_length=1, max_length=128)
    candidate_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    source_item_id: str = Field(min_length=1, max_length=512)
    source_item_version: str | None = Field(default=None, min_length=1, max_length=512)
    original_url: str = Field(min_length=1, max_length=4_096)
    canonical_url: str = Field(min_length=1, max_length=4_096)
    publisher_id: str = Field(min_length=1, max_length=256)
    ownership_group: str | None = Field(default=None, min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=2_000)
    text: str = Field(min_length=1, max_length=2_000_000)
    content_hash: str = Field(min_length=16, max_length=128)
    artifact_ref: str = Field(min_length=1, max_length=512)
    discovered_via: Literal["api", "rss", "atom", "public_page", "cache"]
    content_scope: Literal["summary", "full", "platform_text"]
    raw_published_at: str | None = Field(default=None, max_length=256)
    raw_created_at: str | None = Field(default=None, max_length=256)
    raw_updated_at: str | None = Field(default=None, max_length=256)
    raw_first_seen_at: str | None = Field(default=None, max_length=256)
    published_at: datetime | None = None
    published_interval_end: datetime | None = None
    published_timezone_known: bool = False
    time_precision: Literal["exact", "day", "month", "unknown"] = "unknown"
    updated_at: datetime | None = None
    event_at: datetime | None = None
    first_published_at: datetime | None = None
    first_seen_at: datetime | None = None
    fetched_at: datetime | None = None
    extractor_version: str = Field(min_length=1, max_length=128)
    resource_status: Literal["accepted", "rejected"] = "accepted"
    language: str | None = Field(default=None, min_length=1, max_length=32)
    event_region: str | None = Field(default=None, min_length=1, max_length=128)
    source_role: Literal["primary", "reporting", "discovery", "heat", "unknown"] = (
        "unknown"
    )

    @model_validator(mode="after")
    def validate_publication_time(self) -> SourceDocumentV2:
        timestamps = (
            self.published_at,
            self.published_interval_end,
            self.updated_at,
            self.event_at,
            self.first_published_at,
            self.first_seen_at,
            self.fetched_at,
        )
        if any(
            item is not None
            and (item.tzinfo is None or item.utcoffset() is None)
            for item in timestamps
        ):
            raise ValueError("DOCUMENT_TIME_NAIVE")
        if not self.published_timezone_known and self.published_at is not None:
            raise ValueError("PUBLICATION_TIMEZONE_UNKNOWN")
        if self.published_at is None:
            if self.published_interval_end is not None or self.time_precision == "exact":
                raise ValueError("PUBLICATION_TIME_UNKNOWN")
        elif self.time_precision == "unknown":
            raise ValueError("PUBLICATION_PRECISION_UNKNOWN")
        if self.published_interval_end is not None and (
            self.published_at is None
            or self.published_interval_end <= self.published_at
            or self.time_precision not in {"day", "month"}
        ):
            raise ValueError("PUBLICATION_INTERVAL_INVALID")
        return self


class EvidenceRefV2(_FrozenContract):
    schema_version: Literal["evidence-ref/2"] = "evidence-ref/2"
    evidence_id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(min_length=16, max_length=128)
    paragraph_index: int | None = Field(default=None, ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    excerpt: str = Field(min_length=1, max_length=2_000)
    acquisition_method: Literal["api", "rss", "atom", "public_page", "cache"]

    @model_validator(mode="after")
    def validate_span(self) -> EvidenceRefV2:
        """证据区间使用 Unicode 字符下标且必须与摘录长度一致。"""

        if self.char_start >= self.char_end:
            raise ValueError("EVIDENCE_SPAN_INVALID")
        if self.char_end - self.char_start != len(self.excerpt):
            raise ValueError("EVIDENCE_SPAN_LENGTH_MISMATCH")
        return self


class EventClusterV2(_FrozenContract):
    schema_version: Literal["event-cluster/2"] = "event-cluster/2"
    event_id: str = Field(min_length=1, max_length=128)
    event_type: str = Field(min_length=1, max_length=128)
    entity_names: tuple[str, ...] = Field(default=(), max_length=64)
    event_time: datetime | None = None
    product_version: str | None = Field(default=None, min_length=1, max_length=128)
    member_document_ids: tuple[str, ...] = Field(min_length=1, max_length=256)
    representative_document_id: str = Field(min_length=1, max_length=128)
    merge_basis: tuple[str, ...] = Field(min_length=1, max_length=32)
    cluster_confidence: Literal["confirmed", "uncertain"] = "uncertain"

    @model_validator(mode="after")
    def validate_members(self) -> EventClusterV2:
        if (
            self.representative_document_id not in self.member_document_ids
            or len(set(self.member_document_ids)) != len(self.member_document_ids)
        ):
            raise ValueError("REPRESENTATIVE_NOT_MEMBER")
        if self.event_time is not None and (
            self.event_time.tzinfo is None or self.event_time.utcoffset() is None
        ):
            raise ValueError("EVENT_TIME_NAIVE")
        return self


class ClaimRecordV2(_FrozenContract):
    schema_version: Literal["claim-record/2"] = "claim-record/2"
    claim_id: str = Field(min_length=1, max_length=128)
    claim_key: str = Field(min_length=1, max_length=256)
    event_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4_000)
    claim_type: Literal[
        "announcement", "reported_fact", "measured_result", "opinion", "inference"
    ]
    subject: str = Field(min_length=1, max_length=512)
    value_text: str | None = Field(default=None, max_length=512)
    numeric_value: Decimal | None = None
    unit: str | None = Field(default=None, max_length=64)
    claim_time: datetime | None = None
    assertion_mode: Literal["attributed", "objective", "inference"]
    attributed_to: str | None = Field(default=None, min_length=1, max_length=512)
    support_refs: tuple[str, ...] = Field(min_length=1, max_length=64)
    source_family_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    independent_support_count: int = Field(ge=0, le=64)
    conflict_status: Literal["none", "resolved", "unresolved"] = "none"

    @model_validator(mode="after")
    def validate_claim_shape(self) -> ClaimRecordV2:
        if self.claim_time is not None and (
            self.claim_time.tzinfo is None or self.claim_time.utcoffset() is None
        ):
            raise ValueError("CLAIM_TIME_NAIVE")
        if self.numeric_value is not None and (
            self.value_text is None or self.unit is None or self.claim_time is None
        ):
            raise ValueError("NUMERIC_CLAIM_CONTEXT_REQUIRED")
        if self.assertion_mode == "attributed" and self.attributed_to is None:
            raise ValueError("CLAIM_ATTRIBUTION_REQUIRED")
        if self.assertion_mode != "attributed" and self.attributed_to is not None:
            raise ValueError("CLAIM_ATTRIBUTION_UNEXPECTED")
        if len(set(self.support_refs)) != len(self.support_refs) or len(
            set(self.source_family_ids)
        ) != len(self.source_family_ids):
            raise ValueError("CLAIM_SUPPORT_DUPLICATED")
        if self.independent_support_count > len(self.source_family_ids):
            raise ValueError("CLAIM_INDEPENDENT_SUPPORT_INVALID")
        return self


class CoverageSnapshotV2(_FrozenContract):
    schema_version: Literal["coverage-snapshot/2"] = "coverage-snapshot/2"
    required_facets: tuple[str, ...] = Field(default=(), max_length=64)
    covered_facets: tuple[str, ...] = Field(default=(), max_length=64)
    missing_facets: tuple[str, ...] = Field(default=(), max_length=64)
    historical_coverage: Literal["complete", "partial", "unknown"] = "unknown"


class EvidenceSnapshotV2(_FrozenContract):
    schema_version: Literal["evidence-snapshot/2"] = "evidence-snapshot/2"
    snapshot_id: str = Field(min_length=1, max_length=128)
    brief_digest: str = Field(min_length=16, max_length=128)
    documents: tuple[SourceDocumentV2, ...] = Field(default=(), max_length=2_000)
    events: tuple[EventClusterV2, ...] = Field(default=(), max_length=1_000)
    claims: tuple[ClaimRecordV2, ...] = Field(default=(), max_length=10_000)
    evidence_refs: tuple[EvidenceRefV2, ...] = Field(default=(), max_length=20_000)
    coverage: CoverageSnapshotV2


# 研究端口的中立短名称。
SourceDocument = SourceDocumentV2
EventCluster = EventClusterV2
ClaimRecord = ClaimRecordV2
EvidenceRef = EvidenceRefV2
Coverage = CoverageSnapshotV2


__all__ = [
    "ClaimRecord",
    "ClaimRecordV2",
    "Coverage",
    "CoverageSnapshotV2",
    "EventCluster",
    "EventClusterV2",
    "EvidenceRef",
    "EvidenceRefV2",
    "EvidenceSnapshotV2",
    "SourceDocument",
    "SourceDocumentV2",
]
