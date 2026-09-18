"""READY IntentFrame 到 ResearchBrief 的确定性桥接与缓存资格判断。"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)
from efficiency_platform_agent.contracts.intent_v2 import (
    FieldValue,
    GoalNodeV2,
    IntentFrameV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    CountPolicy,
    ResearchBriefV2,
    ResearchPolicySnapshotV2,
    ResearchRequirementDimension,
    TrustedResearchContextV2,
    build_research_requirement,
)
from efficiency_platform_agent.contracts.temporal_v2 import (
    ResolvedTimeWindow,
    TemporalExpression,
    UnspecifiedTemporalExpression,
)

from .temporal import TemporalResolutionError, TemporalResolver

ResearchBridgeErrorCode = Literal[
    "INTENT_NOT_READY",
    "RESEARCH_GOAL_AMBIGUOUS",
    "RESEARCH_GOAL_REQUIRED",
    "RESEARCH_TOPIC_REQUIRED",
    "RESEARCH_TIME_REQUIRED",
    "RESEARCH_SOURCE_CONSTRAINTS_REQUIRED",
    "RESEARCH_OUTPUT_REQUIREMENTS_REQUIRED",
    "RESEARCH_COUNT_INVALID",
    "TRUSTED_TASK_MISMATCH",
    "TIME_AMBIGUOUS",
    "TIME_INVALID",
]


class ResearchBridgeError(ValueError):
    def __init__(self, code: ResearchBridgeErrorCode) -> None:
        self.code = code
        super().__init__(code)


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResearchCacheEntryV2(_FrozenContract):
    """证据缓存资格所需的最小可信元数据，不承载证据正文。"""

    schema_version: Literal["research-cache-entry/2"] = "research-cache-entry/2"
    cache_entry_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    permission_snapshot_version: str = Field(min_length=1, max_length=128)
    topic_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    entities: tuple[str, ...] = Field(default=(), max_length=64)
    exclusions: tuple[str, ...] = Field(default=(), max_length=64)
    covered_time_window: ResolvedTimeWindow
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=1_000)
    languages: tuple[str, ...] = Field(default=(), max_length=32)
    event_regions: tuple[str, ...] = Field(default=(), max_length=64)
    publisher_regions: tuple[str, ...] = Field(default=(), max_length=64)
    primary_only: bool
    expires_at: datetime

    @field_validator(
        "entities",
        "exclusions",
        "source_ids",
        "languages",
        "event_regions",
        "publisher_regions",
    )
    @classmethod
    def validate_identifiers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value) or len(set(value)) != len(value):
            raise ValueError("CACHE_METADATA_INVALID")
        return value

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("CACHE_EXPIRY_NAIVE")
        return value


class EvidenceReuseDecisionV2(_FrozenContract):
    reusable: bool
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def validate_outcome(self) -> EvidenceReuseDecisionV2:
        if self.reusable == bool(self.reason_codes):
            raise ValueError("CACHE_REUSE_DECISION_INVALID")
        return self


class ResearchBriefBuilderV2:
    """只桥接完整语义，不推测缺失时间、身份或来源。"""

    def __init__(self, temporal_resolver: TemporalResolver | None = None) -> None:
        self.temporal_resolver = temporal_resolver or TemporalResolver()

    def build(
        self,
        frame: IntentFrameV2,
        trusted_context: TrustedResearchContextV2,
        policy_snapshot: ResearchPolicySnapshotV2,
    ) -> ResearchBriefV2:
        if not isinstance(frame, IntentFrameV2):
            raise TypeError("frame 必须是 IntentFrameV2")
        if not isinstance(trusted_context, TrustedResearchContextV2):
            raise TypeError("trusted_context 必须是 TrustedResearchContextV2")
        if not isinstance(policy_snapshot, ResearchPolicySnapshotV2):
            raise TypeError("policy_snapshot 必须是 ResearchPolicySnapshotV2")
        if trusted_context.task_id != frame.task_id:
            raise ResearchBridgeError("TRUSTED_TASK_MISMATCH")
        if frame.unresolved_references or any(
            item.blocking for item in frame.ambiguities
        ):
            raise ResearchBridgeError("INTENT_NOT_READY")

        research_goals = tuple(
            goal
            for goal in frame.goal_nodes
            if OperationSpecialistCapabilityId.RESEARCH_INSIGHT.value
            in goal.candidate_capability_ids
        )
        if not research_goals:
            raise ResearchBridgeError("RESEARCH_GOAL_REQUIRED")
        if any(
            goal.candidate_capability_ids
            != (OperationSpecialistCapabilityId.RESEARCH_INSIGHT.value,)
            for goal in research_goals
        ):
            raise ResearchBridgeError("RESEARCH_GOAL_AMBIGUOUS")
        if frame.revision < 1:
            raise ResearchBridgeError("INTENT_NOT_READY")
        topic = _required_field(frame.topic, "RESEARCH_TOPIC_REQUIRED")
        if not topic.strip():
            raise ResearchBridgeError("RESEARCH_TOPIC_REQUIRED")
        temporal: TemporalExpression = _required_field(
            frame.temporal, "RESEARCH_TIME_REQUIRED"
        )
        if isinstance(temporal, UnspecifiedTemporalExpression):
            raise ResearchBridgeError("RESEARCH_TIME_REQUIRED")
        source_constraints = _required_field(
            frame.source_constraints,
            "RESEARCH_SOURCE_CONSTRAINTS_REQUIRED",
        )
        output_requirements = _required_field(
            frame.output_requirements,
            "RESEARCH_OUTPUT_REQUIREMENTS_REQUIRED",
        )
        try:
            time_window = self.temporal_resolver.resolve(
                temporal,
                frame.anchor_time,
                frame.timezone,
            )
        except TemporalResolutionError as exc:
            raise ResearchBridgeError(exc.code) from exc

        count_policy, count_diagnostics = _count_policy(research_goals)
        entities = tuple(
            item.canonical_name or item.raw_text
            for item in (_optional_field(frame.entities) or ())
        )
        exclusion_values = _optional_field(frame.exclusions)
        exclusions: tuple[str, ...] = exclusion_values or ()
        requirement_values: list[tuple[ResearchRequirementDimension, object]] = [
            ("topic", topic),
            ("time_window", time_window),
            ("source_constraints", source_constraints),
            ("output_requirements", output_requirements),
            ("count_policy", count_policy),
        ]
        if exclusions:
            requirement_values.append(("exclusions", exclusions))
        hard_requirements = tuple(
            build_research_requirement(dimension, value)
            for dimension, value in requirement_values
        )
        return ResearchBriefV2(
            trusted_context=trusted_context,
            intent_revision=frame.revision,
            intent_scope_hash=frame.scope_hash,
            topic=topic,
            entities=entities,
            exclusions=exclusions,
            time_window=time_window,
            source_constraints=source_constraints,
            count_policy=count_policy,
            output_requirements=output_requirements,
            quality_policy_id=policy_snapshot.quality_policy_id,
            policy_version=policy_snapshot.policy_version,
            hard_requirements=hard_requirements,
            diagnostics=_diagnostics(frame, count_diagnostics),
        )


class EvidenceReusePolicyV2:
    """仅在缓存能证明完整覆盖新研究范围时允许复用。"""

    @staticmethod
    def topic_digest(topic: str) -> str:
        normalized = " ".join(topic.casefold().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def evaluate(
        self,
        entry: ResearchCacheEntryV2,
        brief: ResearchBriefV2,
        *,
        tenant_id: str,
        permission_snapshot_version: str,
        now: datetime,
    ) -> EvidenceReuseDecisionV2:
        if not isinstance(entry, ResearchCacheEntryV2):
            raise TypeError("entry 必须是 ResearchCacheEntryV2")
        if not isinstance(brief, ResearchBriefV2):
            raise TypeError("brief 必须是 ResearchBriefV2")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("CACHE_NOW_NAIVE")
        checks = (
            (entry.tenant_id != tenant_id, "CACHE_TENANT_MISMATCH"),
            (
                entry.permission_snapshot_version != permission_snapshot_version,
                "CACHE_PERMISSION_MISMATCH",
            ),
            (now >= entry.expires_at, "CACHE_EXPIRED"),
            (
                entry.topic_digest != self.topic_digest(brief.topic)
                or entry.entities != brief.entities
                or entry.exclusions != brief.exclusions,
                "CACHE_TOPIC_MISMATCH",
            ),
            (
                not _time_covers(entry.covered_time_window, brief.time_window),
                "CACHE_TIME_NOT_COVERED",
            ),
            (not _sources_cover(entry, brief), "CACHE_SOURCE_MISMATCH"),
        )
        for failed, code in checks:
            if failed:
                return EvidenceReuseDecisionV2(reusable=False, reason_codes=(code,))
        return EvidenceReuseDecisionV2(reusable=True)


def _required_field[T](
    field: FieldValue[T] | None,
    code: ResearchBridgeErrorCode,
) -> T:
    if field is None or field.validation != "valid":
        raise ResearchBridgeError(code)
    value = field.value
    if value is None:
        raise ResearchBridgeError(code)
    return value


def _optional_field[T](field: FieldValue[T] | None) -> T | None:
    if field is None:
        return None
    if field.validation != "valid":
        raise ResearchBridgeError("INTENT_NOT_READY")
    return field.value


def _count_policy(
    goals: tuple[GoalNodeV2, ...],
) -> tuple[CountPolicy, tuple[str, ...]]:
    counts = {
        parameter.value
        for goal in goals
        for parameter in getattr(goal, "parameters", ())
        if parameter.name == "count"
    }
    if not counts:
        return (
            CountPolicy(mode="best_effort", target=5, minimum=1),
            ("DEFAULT_COUNT_POLICY:best_effort:5:1",),
        )
    if len(counts) != 1:
        raise ResearchBridgeError("RESEARCH_COUNT_INVALID")
    count = next(iter(counts))
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 1_000:
        raise ResearchBridgeError("RESEARCH_COUNT_INVALID")
    return CountPolicy(mode="exact", target=count, minimum=count), ()


def _diagnostics(
    frame: IntentFrameV2,
    count_diagnostics: tuple[str, ...],
) -> tuple[str, ...]:
    diagnostics = list(count_diagnostics)
    for field_name in (
        "topic",
        "entities",
        "exclusions",
        "temporal",
        "source_constraints",
        "output_requirements",
    ):
        value = getattr(frame, field_name)
        if value is not None and value.origin == "default":
            diagnostics.append(f"DEFAULT_FIELD:{field_name}:{value.default_policy_id}")
    diagnostics.extend(
        f"DEFAULT_LEAF:{item.field_name}:{item.default_policy_id}"
        for item in frame.leaf_provenance
        if item.origin == "default"
    )
    return tuple(dict.fromkeys(diagnostics))


def _time_covers(cached: ResolvedTimeWindow, requested: ResolvedTimeWindow) -> bool:
    return (
        cached.basis == requested.basis
        and cached.start <= requested.start
        and cached.end >= requested.end
    )


def _sources_cover(entry: ResearchCacheEntryV2, brief: ResearchBriefV2) -> bool:
    constraints = brief.source_constraints
    source_ids = set(entry.source_ids)
    if constraints.allowed_source_ids is not None and not source_ids <= set(
        constraints.allowed_source_ids
    ):
        return False
    if source_ids & set(constraints.excluded_source_ids):
        return False
    if constraints.languages is not None and (
        not entry.languages or not set(entry.languages) <= set(constraints.languages)
    ):
        return False
    if constraints.event_regions is not None and (
        not entry.event_regions
        or not set(entry.event_regions) <= set(constraints.event_regions)
    ):
        return False
    if constraints.publisher_regions is not None and (
        not entry.publisher_regions
        or not set(entry.publisher_regions) <= set(constraints.publisher_regions)
    ):
        return False
    return not constraints.primary_only or entry.primary_only


__all__ = [
    "EvidenceReuseDecisionV2",
    "EvidenceReusePolicyV2",
    "ResearchBridgeError",
    "ResearchBriefBuilderV2",
    "ResearchCacheEntryV2",
]
