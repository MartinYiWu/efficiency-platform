"""研究 V2 的中立需求、质量和交付契约。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.contracts.intent_v2 import (
    OutputRequirementsV2,
    SourceConstraintsV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CountPolicy(_FrozenContract):
    mode: Literal["exact", "at_most", "best_effort"]
    target: int = Field(ge=1, le=1_000)
    minimum: int = Field(ge=1, le=1_000)

    @model_validator(mode="after")
    def validate_order(self) -> CountPolicy:
        if self.minimum > self.target:
            raise ValueError("COUNT_MINIMUM_EXCEEDS_TARGET")
        return self


class TrustedResearchContextV2(_FrozenContract):
    """仅由受信任桥接创建的身份和预算引用。"""

    tenant_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    budget_lease_id: str = Field(min_length=1, max_length=128)


class ResearchPolicySnapshotV2(_FrozenContract):
    schema_version: Literal["research-policy/2"] = "research-policy/2"
    quality_policy_id: str = Field(min_length=1, max_length=128)
    policy_version: str = Field(min_length=1, max_length=128)
    minimum_independent_sources: int = Field(default=1, ge=1, le=16)
    require_primary_for_key_claims: bool = False
    max_collection_rounds: int = Field(default=3, ge=1, le=20)
    max_no_gain_rounds: int = Field(default=1, ge=1, le=5)


type ResearchRequirementDimension = Literal[
    "topic",
    "time_window",
    "source_constraints",
    "output_requirements",
    "count_policy",
    "exclusions",
]


class ResearchRequirementV2(_FrozenContract):
    """一个硬研究维度的稳定、可审计标识。"""

    requirement_id: str = Field(min_length=1, max_length=128)
    dimension: ResearchRequirementDimension
    value_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


def build_research_requirement(
    dimension: ResearchRequirementDimension,
    value: object,
) -> ResearchRequirementV2:
    """按固定 JSON 规范生成稳定硬需求标识。"""

    payload: object
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return ResearchRequirementV2(
        requirement_id=f"req-{dimension.replace('_', '-')}-{digest[:20]}",
        dimension=dimension,
        value_digest=digest,
    )


class ResearchBriefV2(_FrozenContract):
    schema_version: Literal["research-brief/2"] = "research-brief/2"
    trusted_context: TrustedResearchContextV2
    intent_revision: int = Field(ge=1)
    intent_scope_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    topic: str = Field(min_length=1, max_length=2_000)
    entities: tuple[str, ...] = Field(default=(), max_length=64)
    exclusions: tuple[str, ...] = Field(default=(), max_length=64)
    required_facets: tuple[str, ...] = Field(default=(), max_length=64)
    time_window: ResolvedTimeWindow
    source_constraints: SourceConstraintsV2
    count_policy: CountPolicy
    ranking_mode: Literal["importance", "heat", "recency"] = "importance"
    output_requirements: OutputRequirementsV2
    quality_policy_id: str = Field(min_length=1, max_length=128)
    policy_version: str = Field(min_length=1, max_length=128)
    hard_requirements: tuple[ResearchRequirementV2, ...] = Field(
        default=(), max_length=6
    )
    diagnostics: tuple[str, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def validate_hard_requirements(self) -> ResearchBriefV2:
        # C02 创建的旧 V2 快照没有该投影；允许读取但不视为 I06 可执行 Brief。
        if not self.hard_requirements:
            return self
        dimensions = [item.dimension for item in self.hard_requirements]
        identifiers = [item.requirement_id for item in self.hard_requirements]
        if len(set(dimensions)) != len(dimensions):
            raise ValueError("RESEARCH_REQUIREMENT_DIMENSION_DUPLICATED")
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("RESEARCH_REQUIREMENT_ID_DUPLICATED")
        required = {
            "topic",
            "time_window",
            "source_constraints",
            "output_requirements",
            "count_policy",
        }
        if not required.issubset(dimensions):
            raise ValueError("RESEARCH_REQUIREMENT_INCOMPLETE")
        if bool(self.exclusions) != ("exclusions" in dimensions):
            raise ValueError("RESEARCH_EXCLUSION_REQUIREMENT_MISMATCH")
        values: list[tuple[ResearchRequirementDimension, object]] = [
            ("topic", self.topic),
            ("time_window", self.time_window),
            ("source_constraints", self.source_constraints),
            ("output_requirements", self.output_requirements),
            ("count_policy", self.count_policy),
        ]
        if self.exclusions:
            values.append(("exclusions", self.exclusions))
        expected = tuple(
            build_research_requirement(dimension, value) for dimension, value in values
        )
        if self.hard_requirements != expected:
            raise ValueError("RESEARCH_REQUIREMENT_DIGEST_MISMATCH")
        return self

    def canonical_digest(self) -> str:
        """生成排除临时诊断的稳定语义摘要。"""

        canonical = json.dumps(
            self.model_dump(mode="json", exclude={"diagnostics"}),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class QualityGapV2(_FrozenContract):
    gap_id: str = Field(min_length=1, max_length=128)
    requirement_id: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=128)
    detail: str = Field(min_length=1, max_length=2_000)
    recoverable: bool


class QualityReportV2(_FrozenContract):
    schema_version: Literal["quality-report/2"] = "quality-report/2"
    report_id: str = Field(min_length=1, max_length=128)
    brief_digest: str = Field(min_length=16, max_length=128)
    policy_version: str = Field(min_length=1, max_length=128)
    hard_gates_passed: bool
    usable_event_ids: tuple[str, ...] = Field(default=(), max_length=1_000)
    conflict_claim_ids: tuple[str, ...] = Field(default=(), max_length=10_000)
    gaps: tuple[QualityGapV2, ...] = Field(default=(), max_length=256)
    coverage_ratio: float = Field(ge=0.0, le=1.0)
    suggested_actions: tuple[str, ...] = Field(default=(), max_length=64)


class CollectionHistoryV2(_FrozenContract):
    completed_action_ids: tuple[str, ...] = Field(default=(), max_length=10_000)
    attempted_source_ids: tuple[str, ...] = Field(default=(), max_length=1_000)
    rounds: int = Field(ge=0, le=1_000)
    no_gain_rounds: int = Field(ge=0, le=1_000)


class BudgetSnapshotV2(_FrozenContract):
    lease_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=0)
    remaining_calls: int = Field(ge=0)
    remaining_bytes: int = Field(ge=0)


class CollectionActionV2(_FrozenContract):
    action_id: str = Field(min_length=1, max_length=128)
    gap_id: str = Field(min_length=1, max_length=128)
    gap_code: str = Field(min_length=1, max_length=128)
    action_kind: Literal[
        "search_alternative",
        "search_required_facet",
        "locate_primary",
        "fetch_content",
        "verify_time",
        "resolve_conflict",
        "observe_heat",
        "retry_or_alternate",
        "switch_free_source",
        "verify_history",
        "rerender_only",
    ]
    source_id: str = Field(min_length=1, max_length=128)
    requirement_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    query: str = Field(min_length=1, max_length=2_000)
    time_window: ResolvedTimeWindow
    cursor: str | None = Field(default=None, min_length=1, max_length=2_000)
    revision: int = Field(ge=0)


class CollectionPlanV2(_FrozenContract):
    schema_version: Literal["collection-plan/2"] = "collection-plan/2"
    actions: tuple[CollectionActionV2, ...] = Field(default=(), max_length=128)
    stop_reason: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_action_or_stop(self) -> CollectionPlanV2:
        if not self.actions and self.stop_reason is None:
            raise ValueError("COLLECTION_PLAN_EMPTY")
        return self


class DeliveryDraftV2(_FrozenContract):
    draft_id: str = Field(min_length=1, max_length=128)
    brief_digest: str = Field(min_length=16, max_length=128)
    content: str = Field(min_length=1, max_length=200_000)
    event_ids: tuple[str, ...] = Field(default=(), max_length=1_000)
    claim_ids: tuple[str, ...] = Field(default=(), max_length=10_000)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=20_000)
    declared_outcome: Literal["COMPLETE", "PARTIAL", "NO_MATCHES", "FAILED"]
    output_type: str = Field(min_length=1, max_length=128)
    exhaustive_scope_claimed: bool = False
    repair_attempt: int = Field(default=0, ge=0, le=1)


class OutputDecisionV2(_FrozenContract):
    schema_version: Literal["output-decision/2"] = "output-decision/2"
    outcome: Literal["ACCEPT", "REVISE", "RECOLLECT", "REJECT"]
    reason_codes: tuple[str, ...] = Field(default=(), max_length=64)
    unsupported_claim_ids: tuple[str, ...] = Field(default=(), max_length=10_000)


class ResearchUsageV2(_FrozenContract):
    source_requests: int = Field(ge=0)
    model_calls: int = Field(ge=0)
    downloaded_bytes: int = Field(ge=0)


class DeliveryCitationV2(_FrozenContract):
    evidence_id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=4_096)
    title: str = Field(min_length=1, max_length=2_000)
    publisher_id: str = Field(min_length=1, max_length=256)
    source_role: Literal["primary", "reporting", "discovery", "heat", "unknown"]
    excerpt: str = Field(min_length=1, max_length=2_000)
    content_scope: Literal["summary", "full", "platform_text"] | None = None
    verification_status: Literal["verified", "unverified"] = "unverified"
    content_hash: str | None = Field(default=None, min_length=16, max_length=128)
    acquisition_method: Literal["api", "rss", "atom", "public_page", "cache"] | None = (
        None
    )
    published_at: datetime | None = None
    independent_source_group: str | None = Field(default=None, max_length=256)


class DeliveryEventV2(_FrozenContract):
    event_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=2_000)
    event_time: datetime | None = None
    claim_ids: tuple[str, ...] = Field(min_length=1, max_length=10_000)
    claim_texts: tuple[str, ...] = Field(min_length=1, max_length=10_000)
    citations: tuple[DeliveryCitationV2, ...] = Field(min_length=1, max_length=20_000)


class DeliveryPackV2(_FrozenContract):
    schema_version: Literal["delivery-pack/2"] = "delivery-pack/2"
    delivery_id: str = Field(min_length=1, max_length=128)
    brief_digest: str = Field(min_length=16, max_length=128)
    event_ids: tuple[str, ...] = Field(default=(), max_length=1_000)
    claim_ids: tuple[str, ...] = Field(default=(), max_length=10_000)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=20_000)
    outcome: Literal["COMPLETE", "PARTIAL", "NO_MATCHES"]
    display_status: Literal["succeeded", "degraded_succeeded"]
    stop_reason: str = Field(min_length=1, max_length=128)
    requested_count: int = Field(ge=1, le=1_000)
    delivered_event_count: int = Field(ge=0, le=1_000)
    time_window_label: str = Field(min_length=1, max_length=1_000)
    events: tuple[DeliveryEventV2, ...] = Field(default=(), max_length=1_000)
    gap_codes: tuple[str, ...] = Field(default=(), max_length=256)
    content: str = Field(min_length=1, max_length=200_000)
    summary: str | None = Field(default=None, min_length=1, max_length=1_000)
    ranking_basis: Literal["evidence_order"] | None = None
    limitations: tuple[str, ...] = Field(default=(), max_length=128)
    renderer_version: str = Field(min_length=1, max_length=128)
    output_verified: bool = False
    quality_report_id: str | None = Field(default=None, max_length=128)


class ResearchOutcomeV2(_FrozenContract):
    schema_version: Literal["research-outcome/2"] = "research-outcome/2"
    outcome: Literal["COMPLETE", "PARTIAL", "NO_MATCHES", "FAILED"]
    delivery: DeliveryPackV2 | None = None
    usable_event_ids: tuple[str, ...] = Field(default=(), max_length=1_000)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=20_000)
    gaps: tuple[QualityGapV2, ...] = Field(default=(), max_length=256)
    stop_reason: str = Field(min_length=1, max_length=128)
    usage: ResearchUsageV2


class ResearchRuntimeContextV2(_FrozenContract):
    request_id: str = Field(min_length=1, max_length=128)
    started_at: datetime
    deadline: datetime

    @model_validator(mode="after")
    def validate_deadline(self) -> ResearchRuntimeContextV2:
        if self.started_at >= self.deadline:
            raise ValueError("RESEARCH_DEADLINE_INVALID")
        return self


# 计划中的中立短名称。
Quality = QualityReportV2
CollectionPlan = CollectionPlanV2
OutputDecision = OutputDecisionV2
DeliveryPack = DeliveryPackV2


__all__ = [
    "BudgetSnapshotV2",
    "CollectionActionV2",
    "CollectionHistoryV2",
    "CollectionPlan",
    "CollectionPlanV2",
    "CountPolicy",
    "DeliveryCitationV2",
    "DeliveryDraftV2",
    "DeliveryEventV2",
    "DeliveryPack",
    "DeliveryPackV2",
    "OutputDecision",
    "OutputDecisionV2",
    "Quality",
    "QualityGapV2",
    "QualityReportV2",
    "ResearchBriefV2",
    "ResearchOutcomeV2",
    "ResearchPolicySnapshotV2",
    "ResearchRequirementDimension",
    "ResearchRequirementV2",
    "ResearchRuntimeContextV2",
    "ResearchUsageV2",
    "TrustedResearchContextV2",
    "build_research_requirement",
]
