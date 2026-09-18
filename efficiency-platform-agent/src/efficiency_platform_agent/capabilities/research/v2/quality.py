"""从已验证研究事实确定性聚合 H1-H6 与集合质量。"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.capabilities.research.v2.claims import ConflictSetV2
from efficiency_platform_agent.capabilities.research.v2.evidence import (
    EvidenceValidator,
)
from efficiency_platform_agent.capabilities.research.v2.filtering import FilterResultV2
from efficiency_platform_agent.contracts.research_evidence_v2 import (
    ClaimRecordV2,
    EventClusterV2,
    EvidenceRefV2,
    SourceDocumentV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    QualityGapV2,
    QualityReportV2,
    ResearchBriefV2,
    ResearchPolicySnapshotV2,
)


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourcePolicyDecisionV2(_FrozenContract):
    source_id: str = Field(min_length=1, max_length=128)
    allowed: bool
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def validate_status(self) -> SourcePolicyDecisionV2:
        if self.allowed == bool(self.reason_codes):
            raise ValueError("SOURCE_POLICY_DECISION_INVALID")
        return self


class CollectionCoverageV2(_FrozenContract):
    plan_complete: bool
    attempt_count: int = Field(ge=0)
    critical_failure: bool = False
    truncated: bool = False
    historical_coverage: Literal["complete", "partial", "unknown"] = "unknown"
    warning_codes: tuple[str, ...] = Field(default=(), max_length=64)


class EventQualityDecisionV2(_FrozenContract):
    event_id: str = Field(min_length=1, max_length=128)
    passed: bool
    failed_gates: tuple[Literal["H1", "H2", "H3", "H4", "H5", "H6"], ...] = (
        ()
    )
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_status(self) -> EventQualityDecisionV2:
        if self.passed == bool(self.failed_gates) or len(self.failed_gates) != len(
            self.reason_codes
        ):
            raise ValueError("EVENT_QUALITY_DECISION_INVALID")
        return self


class QualityEvaluationV2(_FrozenContract):
    outcome: Literal["COMPLETE", "PARTIAL", "NO_MATCHES", "FAILED"]
    report: QualityReportV2
    event_decisions: tuple[EventQualityDecisionV2, ...] = Field(
        default=(), max_length=2_000
    )
    warning_codes: tuple[str, ...] = Field(default=(), max_length=128)


def evaluate_quality(
    brief: ResearchBriefV2,
    policy: ResearchPolicySnapshotV2,
    documents: tuple[SourceDocumentV2, ...],
    events: tuple[EventClusterV2, ...],
    claims: tuple[ClaimRecordV2, ...],
    evidence_refs: tuple[EvidenceRefV2, ...],
    filters: FilterResultV2,
    conflicts: ConflictSetV2,
    source_decisions: tuple[SourcePolicyDecisionV2, ...],
    collection: CollectionCoverageV2,
) -> QualityEvaluationV2:
    if brief.quality_policy_id != policy.quality_policy_id:
        raise ValueError("QUALITY_POLICY_MISMATCH")
    _validate_unique_inputs(documents, events, claims, evidence_refs, source_decisions)
    document_by_id = {item.document_id: item for item in documents}
    claim_by_event: dict[str, list[ClaimRecordV2]] = {}
    for claim in claims:
        claim_by_event.setdefault(claim.event_id, []).append(claim)
    ref_by_id = {item.evidence_id: item for item in evidence_refs}
    accepted_documents = set(filters.accepted_document_ids)
    source_policy = {item.source_id: item for item in source_decisions}
    duplicate_members = _duplicate_event_members(events)
    unresolved_objective = {
        item.claim_id
        for item in conflicts.claims
        if item.conflict_status == "unresolved" and item.assertion_mode == "objective"
    }
    if {item.claim_id for item in conflicts.claims} != {
        item.claim_id for item in claims
    }:
        raise ValueError("QUALITY_CONFLICT_SNAPSHOT_MISMATCH")
    if any(item.event_id not in {event.event_id for event in events} for item in claims):
        raise ValueError("QUALITY_CLAIM_EVENT_UNKNOWN")
    filter_ids = set(filters.accepted_document_ids).union(
        item.document_id for item in (*filters.rejected, *filters.uncertain)
    )
    if filter_ids != set(document_by_id):
        raise ValueError("QUALITY_FILTER_SNAPSHOT_MISMATCH")
    decisions: list[EventQualityDecisionV2] = []
    for event in events:
        gates: list[Literal["H1", "H2", "H3", "H4", "H5", "H6"]] = []
        reasons: list[str] = []
        members = [document_by_id.get(item) for item in event.member_document_ids]
        event_claims = claim_by_event.get(event.event_id, [])
        if any(item not in accepted_documents for item in event.member_document_ids):
            gates.append("H1")
            reasons.append("EVENT_CONDITION_UNVERIFIED")
        if not _claims_have_complete_content(
            event_claims, ref_by_id, document_by_id
        ):
            gates.append("H2")
            reasons.append("EVENT_CONTENT_INSUFFICIENT")
        if not _claims_have_valid_evidence(
            event_claims, ref_by_id, document_by_id, event, brief, policy
        ):
            gates.append("H3")
            reasons.append("EVENT_EVIDENCE_INVALID")
        if any(item in duplicate_members for item in event.member_document_ids):
            gates.append("H4")
            reasons.append("EVENT_DUPLICATED")
        if any(item.claim_id in unresolved_objective for item in event_claims):
            gates.append("H5")
            reasons.append("EVENT_CONFLICT_UNRESOLVED")
        if any(
            item is None
            or item.source_id not in source_policy
            or not source_policy[item.source_id].allowed
            for item in members
        ):
            gates.append("H6")
            reasons.append("EVENT_SOURCE_NOT_ALLOWED")
        decisions.append(
            EventQualityDecisionV2(
                event_id=event.event_id,
                passed=not gates,
                failed_gates=tuple(gates),
                reason_codes=tuple(reasons),
            )
        )
    usable = tuple(item.event_id for item in decisions if item.passed)
    covered_facets = {
        claim.claim_key for claim in claims if claim.event_id in usable
    }.intersection(brief.required_facets)
    missing_facets = set(brief.required_facets) - covered_facets
    gaps = _collection_gaps(brief, usable, missing_facets)
    outcome = _outcome(events, usable, gaps, collection)
    if not events and outcome != "NO_MATCHES":
        gaps = (*gaps, _gap("collection", "COLLECTION_INCOMPLETE", True))
    digest = brief.canonical_digest()
    report_id = "quality-" + hashlib.sha256(
        (digest + "\x00" + "\x00".join(usable)).encode("utf-8")
    ).hexdigest()[:32]
    coverage_ratio = (
        len(covered_facets) / len(brief.required_facets)
        if brief.required_facets
        else 1.0
    )
    report = QualityReportV2(
        report_id=report_id,
        brief_digest=digest,
        policy_version=policy.policy_version,
        hard_gates_passed=outcome == "COMPLETE",
        usable_event_ids=usable,
        conflict_claim_ids=tuple(sorted(unresolved_objective)),
        gaps=gaps,
        coverage_ratio=coverage_ratio,
        suggested_actions=tuple(sorted({item.code for item in gaps if item.recoverable})),
    )
    return QualityEvaluationV2(
        outcome=outcome,
        report=report,
        event_decisions=tuple(decisions),
        warning_codes=collection.warning_codes,
    )


def _claims_have_valid_evidence(
    claims: list[ClaimRecordV2],
    refs: dict[str, EvidenceRefV2],
    documents: dict[str, SourceDocumentV2],
    event: EventClusterV2,
    brief: ResearchBriefV2,
    policy: ResearchPolicySnapshotV2,
) -> bool:
    if not claims:
        return False
    validator = EvidenceValidator()
    for claim in claims:
        if (
            claim.assertion_mode == "objective"
            and claim.independent_support_count < policy.minimum_independent_sources
        ):
            return False
        if not claim.support_refs:
            return False
        supporting_documents: list[SourceDocumentV2] = []
        for ref_id in claim.support_refs:
            ref = refs.get(ref_id)
            if (
                ref is None
                or ref.document_id not in event.member_document_ids
                or not validator.validate(ref, documents.get(ref.document_id)).valid
            ):
                return False
            supporting_documents.append(documents[ref.document_id])
        if (
            policy.require_primary_for_key_claims
            and claim.claim_key in brief.required_facets
            and not any(item.source_role == "primary" for item in supporting_documents)
        ):
            return False
    return True


def _claims_have_complete_content(
    claims: list[ClaimRecordV2],
    refs: dict[str, EvidenceRefV2],
    documents: dict[str, SourceDocumentV2],
) -> bool:
    if not claims:
        return False
    for claim in claims:
        supporting_documents = [
            documents.get(refs[ref_id].document_id)
            for ref_id in claim.support_refs
            if ref_id in refs
        ]
        if not any(
            item is not None and item.content_scope in {"full", "platform_text"}
            for item in supporting_documents
        ):
            return False
    return True


def _collection_gaps(
    brief: ResearchBriefV2,
    usable: tuple[str, ...],
    missing_facets: set[str],
) -> tuple[QualityGapV2, ...]:
    gaps: list[QualityGapV2] = []
    count = len(usable)
    if brief.count_policy.mode == "exact" and count < brief.count_policy.target:
        gaps.append(_gap("count_policy", "COUNT_EXACT_UNMET", True))
    elif brief.count_policy.mode in {"at_most", "best_effort"} and (
        count < brief.count_policy.minimum
    ):
        gaps.append(_gap("count_policy", "COUNT_MINIMUM_UNMET", True))
    gaps.extend(
        _gap(f"facet:{facet}", "REQUIRED_FACET_UNCOVERED", True)
        for facet in sorted(missing_facets)
    )
    return tuple(gaps)


def _outcome(
    events: tuple[EventClusterV2, ...],
    usable: tuple[str, ...],
    gaps: tuple[QualityGapV2, ...],
    collection: CollectionCoverageV2,
) -> Literal["COMPLETE", "PARTIAL", "NO_MATCHES", "FAILED"]:
    if collection.critical_failure:
        return "FAILED"
    if usable:
        return "PARTIAL" if gaps else "COMPLETE"
    if not events and (
        collection.plan_complete
        and collection.attempt_count > 0
        and not collection.critical_failure
        and not collection.truncated
        and collection.historical_coverage == "complete"
    ):
        return "NO_MATCHES"
    return "FAILED"


def _duplicate_event_members(events: tuple[EventClusterV2, ...]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for event in events:
        for member in event.member_document_ids:
            if member in seen:
                duplicates.add(member)
            seen.add(member)
    return duplicates


def _validate_unique_inputs(
    documents: tuple[SourceDocumentV2, ...],
    events: tuple[EventClusterV2, ...],
    claims: tuple[ClaimRecordV2, ...],
    refs: tuple[EvidenceRefV2, ...],
    source_decisions: tuple[SourcePolicyDecisionV2, ...],
) -> None:
    collections = (
        [item.document_id for item in documents],
        [item.event_id for item in events],
        [item.claim_id for item in claims],
        [item.evidence_id for item in refs],
        [item.source_id for item in source_decisions],
    )
    if any(len(set(items)) != len(items) for items in collections):
        raise ValueError("QUALITY_INPUT_DUPLICATED")


def _gap(requirement_id: str, code: str, recoverable: bool) -> QualityGapV2:
    digest = hashlib.sha256(f"{requirement_id}\x00{code}".encode()).hexdigest()[:24]
    return QualityGapV2(
        gap_id=f"gap-{digest}",
        requirement_id=requirement_id,
        code=code,
        detail=code,
        recoverable=recoverable,
    )


__all__ = [
    "CollectionCoverageV2",
    "EventQualityDecisionV2",
    "QualityEvaluationV2",
    "SourcePolicyDecisionV2",
    "evaluate_quality",
]
