"""免费来源准入、发现、获取与抽取的中立契约。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceCostPolicyV2(_FrozenContract):
    mode: Literal["free", "free_quota", "paid", "unknown"]
    evidence_url: str = Field(min_length=1, max_length=4_096)
    verified_at: datetime
    quota_limit: int | None = Field(default=None, ge=1)
    quota_period: Literal["minute", "hour", "day", "month"] | None = None
    requires_authentication: bool
    overage_behavior: Literal["hard_stop", "charge", "unknown"]

    @model_validator(mode="after")
    def validate_free_quota(self) -> SourceCostPolicyV2:
        if self.mode == "free_quota" and (
            self.quota_limit is None
            or self.quota_period is None
            or self.overage_behavior != "hard_stop"
        ):
            raise ValueError("FREE_QUOTA_HARD_STOP_REQUIRED")
        return self


class SourceContentPolicyV2(_FrozenContract):
    storage_mode: Literal["full", "excerpt_only", "metadata_only"]
    retention_days: int | None = Field(default=None, ge=1, le=36_500)
    citation_allowed: bool
    access_restriction: str | None = Field(default=None, max_length=1_000)


class SourceRatePolicyV2(_FrozenContract):
    requests: int = Field(ge=1, le=1_000_000)
    period_seconds: int = Field(ge=1, le=2_592_000)
    concurrency: int = Field(default=1, ge=1, le=128)


class SourceAdmissionRecordV2(_FrozenContract):
    admission_record_id: str = Field(min_length=1, max_length=128)
    status: Literal["VERIFIED", "UNVERIFIED", "BLOCKED"]
    last_verified_at: datetime | None = None
    approved_by: str | None = Field(default=None, min_length=1, max_length=128)
    intended_uses: tuple[str, ...] = Field(default=(), max_length=32)
    schema_verified: bool = False
    history_verified: bool = False
    permission_verified: bool = False
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_verified_record(self) -> SourceAdmissionRecordV2:
        if self.status == "VERIFIED" and (
            self.last_verified_at is None
            or self.approved_by is None
            or not self.schema_verified
            or not self.permission_verified
        ):
            raise ValueError("VERIFIED_ADMISSION_INCOMPLETE")
        return self


class SourceDescriptorV2(_FrozenContract):
    schema_version: Literal["source-descriptor/2"] = "source-descriptor/2"
    source_id: str = Field(min_length=1, max_length=128)
    adapter_id: str = Field(min_length=1, max_length=128)
    config_version: str = Field(min_length=1, max_length=128)
    roles: tuple[Literal["primary", "reporting", "discovery", "heat"], ...] = Field(
        default=("discovery",), min_length=1, max_length=4
    )
    topics: tuple[str, ...] = Field(default=(), max_length=64)
    languages: tuple[str, ...] = Field(default=(), max_length=16)
    regions: tuple[str, ...] = Field(default=(), max_length=32)
    publisher_id: str = Field(min_length=1, max_length=256)
    ownership_group: str | None = Field(default=None, min_length=1, max_length=256)
    allowed_hosts: tuple[str, ...] = Field(min_length=1, max_length=32)
    # 正文准入的静态完整 URL；路径及查询串逐字匹配，空集合不授权获取正文。
    content_endpoints: tuple[str, ...] = Field(default=(), max_length=512)
    access_mode: Literal["api", "rss", "atom", "public_page"]
    history_mode: Literal["queryable", "archive", "latest_only", "unknown"]
    max_lookback: timedelta | None = None
    pagination: bool
    freshness_sla: timedelta | None = None
    rate_policy: SourceRatePolicyV2
    content_policy: SourceContentPolicyV2
    cost_policy: SourceCostPolicyV2
    admission: SourceAdmissionRecordV2
    enabled: bool


class SourceRuntimeContextV2(_FrozenContract):
    tenant_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    now: datetime
    allowed_source_ids: tuple[str, ...] | None = Field(default=None, max_length=256)
    available_credential_source_ids: tuple[str, ...] = Field(default=(), max_length=256)
    quota_remaining_by_source: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_runtime_scope(self) -> SourceRuntimeContextV2:
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("SOURCE_RUNTIME_NOW_NAIVE")
        for values in (
            self.allowed_source_ids,
            self.available_credential_source_ids,
        ):
            if values is not None and (
                any(not item.strip() for item in values)
                or len(set(values)) != len(values)
            ):
                raise ValueError("SOURCE_RUNTIME_SCOPE_INVALID")
        if any(
            not source_id.strip() or isinstance(remaining, bool) or remaining < 0
            for source_id, remaining in self.quota_remaining_by_source.items()
        ):
            raise ValueError("SOURCE_RUNTIME_QUOTA_INVALID")
        return self


class DiscoveryRequestV2(_FrozenContract):
    request_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    lease_id: str = Field(min_length=1, max_length=128)
    authorization_scope_digest: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    brief_digest: str = Field(min_length=16, max_length=128)
    query: str = Field(min_length=1, max_length=2_000)
    time_window: ResolvedTimeWindow
    cursor: str | None = Field(default=None, min_length=1, max_length=2_000)
    limit: int = Field(ge=1, le=500)


class CandidateRecordV2(_FrozenContract):
    candidate_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    source_item_id: str = Field(min_length=1, max_length=512)
    source_item_version: str | None = Field(default=None, min_length=1, max_length=512)
    url: str = Field(min_length=1, max_length=4_096)
    title: str = Field(min_length=1, max_length=2_000)
    raw_published_at: str | None = Field(default=None, max_length=256)
    raw_created_at: str | None = Field(default=None, max_length=256)
    raw_updated_at: str | None = Field(default=None, max_length=256)
    raw_first_seen_at: str | None = Field(default=None, max_length=256)
    timestamp_semantics: Literal[
        "published", "updated", "platform_posted", "unknown"
    ] = "unknown"
    discovered_via: Literal["api", "rss", "atom", "public_page", "cache"]
    heat_observation: str | None = Field(default=None, max_length=1_000)
    content_scope: Literal["none", "summary", "full", "platform_text"] = "none"
    inline_content: str | None = Field(default=None, max_length=2_000_000)
    labels: tuple[str, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_inline_content(self) -> CandidateRecordV2:
        if any(
            value is not None and not value.strip()
            for value in (
                self.raw_published_at,
                self.raw_created_at,
                self.raw_updated_at,
                self.raw_first_seen_at,
                self.heat_observation,
            )
        ):
            raise ValueError("CANDIDATE_METADATA_BLANK")
        if self.content_scope == "none" and self.inline_content is not None:
            raise ValueError("CANDIDATE_CONTENT_SCOPE_INVALID")
        if self.content_scope != "none" and (
            self.inline_content is None or not self.inline_content.strip()
        ):
            raise ValueError("CANDIDATE_INLINE_CONTENT_REQUIRED")
        if (
            any(not item.strip() or len(item) > 128 for item in self.labels)
            or len(set(self.labels)) != len(self.labels)
        ):
            raise ValueError("CANDIDATE_LABEL_INVALID")
        if self.timestamp_semantics in {"published", "platform_posted"} and (
            self.raw_published_at is None
        ):
            raise ValueError("CANDIDATE_TIMESTAMP_SEMANTICS_INVALID")
        if self.timestamp_semantics == "updated" and self.raw_updated_at is None:
            raise ValueError("CANDIDATE_TIMESTAMP_SEMANTICS_INVALID")
        return self


class DiscoveryBatchV2(_FrozenContract):
    request_id: str = Field(min_length=1, max_length=128)
    candidates: tuple[CandidateRecordV2, ...] = Field(default=(), max_length=500)
    next_cursor: str | None = Field(default=None, min_length=1, max_length=2_000)
    completeness: Literal["complete", "truncated", "unknown"]
    coverage: Literal["complete", "partial", "unknown"]
    attempts: tuple[SourceAttemptV2, ...] = Field(min_length=1, max_length=64)


class FetchRequestV2(_FrozenContract):
    request_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    lease_id: str = Field(min_length=1, max_length=128)
    authorization_scope_digest: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    candidate_id: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=4_096)
    etag: str | None = Field(default=None, max_length=512)
    last_modified: str | None = Field(default=None, max_length=512)


class FetchedContentV2(_FrozenContract):
    request_id: str = Field(min_length=1, max_length=128)
    candidate_id: str = Field(min_length=1, max_length=128)
    final_url: str = Field(min_length=1, max_length=4_096)
    media_type: str = Field(min_length=1, max_length=256)
    body: bytes = Field(max_length=10_000_000)
    downloaded_bytes: int = Field(ge=0)
    request_count: int = Field(default=1, ge=1, le=64)
    fetched_at: datetime
    status_code: int = Field(ge=100, le=599)
    etag: str | None = Field(default=None, max_length=512)
    last_modified: str | None = Field(default=None, max_length=512)
    response_headers: tuple[tuple[str, str], ...] = Field(default=(), max_length=32)
    cache_status: Literal["miss", "revalidated"] = "miss"

    @field_validator("response_headers")
    @classmethod
    def validate_response_headers(
        cls, value: tuple[tuple[str, str], ...]
    ) -> tuple[tuple[str, str], ...]:
        names = [name.lower() for name, _ in value]
        if (
            len(set(names)) != len(names)
            or any(
                not name
                or len(name) > 128
                or any(
                    not character.isascii()
                    or not (character.isalnum() or character == "-")
                    for character in name
                )
                for name, _ in value
            )
            or any(
                len(header_value) > 4_096
                or any(ord(character) < 32 or ord(character) == 127 for character in header_value)
                for _, header_value in value
            )
        ):
            raise ValueError("FETCHED_RESPONSE_HEADERS_INVALID")
        return tuple((name.lower(), header_value) for name, header_value in value)


class ExtractedDocumentV2(_FrozenContract):
    candidate_id: str = Field(min_length=1, max_length=128)
    canonical_url: str = Field(min_length=1, max_length=4_096)
    title: str = Field(min_length=1, max_length=2_000)
    text: str = Field(min_length=1, max_length=2_000_000)
    content_hash: str = Field(min_length=16, max_length=128)
    published_at: datetime | None = None
    extractor_version: str = Field(min_length=1, max_length=128)


class SourceUsageV2(_FrozenContract):
    requests: int = Field(ge=0)
    returned_items: int = Field(ge=0)
    downloaded_bytes: int = Field(ge=0)


class SourceAttemptV2(_FrozenContract):
    attempt_id: str = Field(min_length=1, max_length=128)
    action_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    status: Literal["success", "success_empty", "failed", "truncated", "cancelled"]
    started_at: datetime
    finished_at: datetime | None = None
    returned_count: int = Field(ge=0)
    filtered_count: int = Field(ge=0)
    error_code: str | None = Field(default=None, max_length=128)
    coverage: Literal["complete", "partial", "unknown"] = "unknown"
    cursor: str | None = Field(default=None, max_length=2_000)
    http_status: int | None = Field(default=None, ge=100, le=599)
    rate_limit_remaining: int | None = Field(default=None, ge=0)
    retry_after_seconds: int | None = Field(default=None, ge=0, le=86_400)
    lease_id: str | None = Field(default=None, min_length=1, max_length=128)
    usage: SourceUsageV2

    @model_validator(mode="after")
    def validate_status(self) -> SourceAttemptV2:
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("ATTEMPT_TIME_INVALID")
        if self.status == "success_empty" and self.returned_count != 0:
            raise ValueError("SUCCESS_EMPTY_HAS_ITEMS")
        if self.status == "failed" and self.error_code is None:
            raise ValueError("FAILED_ERROR_REQUIRED")
        return self


DiscoveryBatchV2.model_rebuild()


# 端口签名使用的中立短名称，具体版本仍由同一 Pydantic 模型冻结。
SourceDescriptor = SourceDescriptorV2
DiscoveryRequest = DiscoveryRequestV2
DiscoveryBatch = DiscoveryBatchV2
FetchRequest = FetchRequestV2
FetchedContent = FetchedContentV2
ExtractedDocument = ExtractedDocumentV2
SourceAttempt = SourceAttemptV2


__all__ = [
    "CandidateRecordV2",
    "DiscoveryBatch",
    "DiscoveryBatchV2",
    "DiscoveryRequest",
    "DiscoveryRequestV2",
    "ExtractedDocument",
    "ExtractedDocumentV2",
    "FetchRequest",
    "FetchRequestV2",
    "FetchedContent",
    "FetchedContentV2",
    "SourceAdmissionRecordV2",
    "SourceAttempt",
    "SourceAttemptV2",
    "SourceContentPolicyV2",
    "SourceCostPolicyV2",
    "SourceDescriptor",
    "SourceDescriptorV2",
    "SourceRatePolicyV2",
    "SourceRuntimeContextV2",
    "SourceUsageV2",
]
