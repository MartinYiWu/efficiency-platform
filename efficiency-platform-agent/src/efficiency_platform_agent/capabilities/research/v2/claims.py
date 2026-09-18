"""Claim 模型提案的确定性证据、数值、归属和冲突门禁。"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.capabilities.research.v2.evidence import (
    EvidenceContextV2,
    EvidenceValidator,
)
from efficiency_platform_agent.contracts.intent_v2 import BudgetLeaseReferenceV2
from efficiency_platform_agent.contracts.research_evidence_v2 import (
    ClaimRecordV2,
    EventClusterV2,
    EvidenceRefV2,
    SourceDocumentV2,
)

CLAIMS_PROMPT_VERSION = "research.v2.claims@1.0.0"
_NUMBER_PATTERN = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?![\w.])")
_UNIT_MARKERS: dict[str, tuple[str, ...]] = {
    "percent": ("%", "percent", "percentage", "百分"),
    "seconds": ("秒", "second", "seconds", "sec", "s"),
    "milliseconds": ("毫秒", "millisecond", "milliseconds", "ms"),
    "usd": ("$", "usd", "美元"),
    "cny": ("¥", "cny", "人民币", "元"),
}


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ClaimProposalV2(_FrozenContract):
    proposal_id: str = Field(min_length=1, max_length=512)
    claim_key: str = Field(min_length=1, max_length=256)
    brief_digest: str = Field(min_length=64, max_length=64)
    prompt_version: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4_000)
    claim_type: Literal[
        "announcement", "reported_fact", "measured_result", "opinion", "inference"
    ]
    subject: str = Field(min_length=1, max_length=512)
    value_text: str | None = Field(default=None, max_length=512)
    numeric_value: Decimal | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=64)
    claim_time: datetime | None = None
    assertion_mode: Literal["attributed", "objective", "inference"]
    attributed_to: str | None = Field(default=None, min_length=1, max_length=512)
    support_refs: tuple[str, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_shape(self) -> ClaimProposalV2:
        if self.claim_time is not None and (
            self.claim_time.tzinfo is None or self.claim_time.utcoffset() is None
        ):
            raise ValueError("CLAIM_TIME_NAIVE")
        if len(set(self.support_refs)) != len(self.support_refs):
            raise ValueError("CLAIM_SUPPORT_DUPLICATED")
        return self


class RejectedClaimV2(_FrozenContract):
    proposal_id: str = Field(min_length=1, max_length=512)
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=16)


class ClaimBatchV2(_FrozenContract):
    accepted: tuple[ClaimRecordV2, ...] = Field(default=(), max_length=10_000)
    rejected: tuple[RejectedClaimV2, ...] = Field(default=(), max_length=10_000)
    input_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> ClaimBatchV2:
        if self.input_count != len(self.accepted) + len(self.rejected):
            raise ValueError("CLAIM_BATCH_COUNT_INVALID")
        return self


class ClaimRecallMetricsV2(_FrozenContract):
    recall: float = Field(ge=0.0, le=1.0)
    expected_count: int = Field(ge=0)
    proposed_count: int = Field(ge=0)
    missing_claim_keys: tuple[str, ...] = Field(default=(), max_length=10_000)
    unexpected_claim_keys: tuple[str, ...] = Field(default=(), max_length=10_000)


class ConflictGroupV2(_FrozenContract):
    conflict_id: str = Field(min_length=1, max_length=128)
    claim_ids: tuple[str, ...] = Field(min_length=2, max_length=1_000)
    status: Literal["unresolved"] = "unresolved"
    distinct_values: tuple[str, ...] = Field(min_length=2, max_length=1_000)


class ConflictSetV2(_FrozenContract):
    claims: tuple[ClaimRecordV2, ...] = Field(default=(), max_length=10_000)
    groups: tuple[ConflictGroupV2, ...] = Field(default=(), max_length=10_000)
    certain_fact_claim_ids: tuple[str, ...] = Field(default=(), max_length=10_000)
    attributed_dispute_claim_ids: tuple[str, ...] = Field(
        default=(), max_length=10_000
    )


@runtime_checkable
class ClaimDecisionPort(Protocol):
    async def propose(
        self,
        events: tuple[EventClusterV2, ...],
        evidence_context: EvidenceContextV2,
        lease: BudgetLeaseReferenceV2,
    ) -> tuple[ClaimProposalV2, ...]: ...


class ClaimExtractor:
    def __init__(self, decision_port: ClaimDecisionPort) -> None:
        if not isinstance(decision_port, ClaimDecisionPort):
            raise TypeError("decision_port 必须实现 ClaimDecisionPort")
        self._decision_port = decision_port
        self._validator = EvidenceValidator()

    async def extract(
        self,
        events: tuple[EventClusterV2, ...],
        evidence_context: EvidenceContextV2,
        lease: BudgetLeaseReferenceV2,
    ) -> ClaimBatchV2:
        if not isinstance(evidence_context, EvidenceContextV2):
            raise TypeError("evidence_context 类型无效")
        if not isinstance(lease, BudgetLeaseReferenceV2):
            raise TypeError("lease 类型无效")
        event_by_id = {item.event_id: item for item in events}
        if len(event_by_id) != len(events):
            raise ValueError("CLAIM_EVENT_DUPLICATED")
        proposals = await self._decision_port.propose(events, evidence_context, lease)
        if not isinstance(proposals, tuple) or any(
            not isinstance(item, ClaimProposalV2) for item in proposals
        ):
            raise TypeError("CLAIM_PROPOSALS_INVALID")
        proposal_ids = [item.proposal_id for item in proposals]
        if len(set(proposal_ids)) != len(proposal_ids):
            raise ValueError("CLAIM_PROPOSAL_DUPLICATED")

        documents = {item.document_id: item for item in evidence_context.documents}
        refs = {item.evidence_id: item for item in evidence_context.evidence_refs}
        families_by_document = {
            document_id: family
            for family in evidence_context.source_families.families
            for document_id in family.member_document_ids
        }
        accepted: list[ClaimRecordV2] = []
        rejected: list[RejectedClaimV2] = []
        for proposal in proposals:
            reasons = _validate_proposal(
                proposal,
                evidence_context,
                event_by_id,
                documents,
                refs,
                self._validator,
            )
            if reasons:
                rejected.append(
                    RejectedClaimV2(
                        proposal_id=proposal.proposal_id,
                        reason_codes=reasons,
                    )
                )
                continue
            supporting_documents = {
                refs[ref_id].document_id for ref_id in proposal.support_refs
            }
            families = {
                families_by_document[document_id].family_id
                for document_id in supporting_documents
            }
            independent = sum(
                family.independence_status == "confirmed"
                for family in evidence_context.source_families.families
                if family.family_id in families
            )
            accepted.append(
                _claim_record(proposal, tuple(sorted(families)), independent)
            )
        return ClaimBatchV2(
            accepted=tuple(accepted),
            rejected=tuple(rejected),
            input_count=len(proposals),
        )


def _validate_proposal(
    proposal: ClaimProposalV2,
    context: EvidenceContextV2,
    event_by_id: dict[str, EventClusterV2],
    documents: dict[str, SourceDocumentV2],
    refs: dict[str, EvidenceRefV2],
    validator: EvidenceValidator,
) -> tuple[str, ...]:
    if (
        proposal.brief_digest != context.brief_digest
        or proposal.prompt_version != CLAIMS_PROMPT_VERSION
    ):
        return ("CLAIM_PROPOSAL_STALE",)
    event = event_by_id.get(proposal.event_id)
    if event is None:
        return ("CLAIM_EVENT_UNKNOWN",)
    if any(ref_id not in refs for ref_id in proposal.support_refs):
        return ("CLAIM_EVIDENCE_UNKNOWN",)

    selected_refs = tuple(refs[item] for item in proposal.support_refs)
    if any(
        not validator.validate(ref, documents.get(ref.document_id)).valid
        for ref in selected_refs
    ):
        return ("CLAIM_EVIDENCE_INVALID",)
    if any(ref.document_id not in event.member_document_ids for ref in selected_refs):
        return ("CLAIM_EVIDENCE_OUTSIDE_EVENT",)
    evidence_text = "\n".join(ref.excerpt for ref in selected_refs)
    if proposal.subject.casefold() not in evidence_text.casefold():
        return ("CLAIM_SUBJECT_UNSUPPORTED",)
    if proposal.numeric_value is not None:
        if proposal.value_text is None or proposal.unit is None or proposal.claim_time is None:
            return ("CLAIM_NUMERIC_CONTEXT_MISSING",)
        if proposal.numeric_value not in _numbers(evidence_text):
            return ("CLAIM_NUMBER_UNSUPPORTED",)
        if (
            proposal.numeric_value not in _numbers(proposal.value_text)
            or proposal.numeric_value not in _numbers(proposal.text)
        ):
            return ("CLAIM_VALUE_INCONSISTENT",)
        if not _unit_supported(
            proposal.unit, evidence_text
        ) or not _unit_supported(proposal.unit, proposal.text):
            return ("CLAIM_UNIT_UNSUPPORTED",)
    attribution_error = _attribution_error(
        proposal,
        tuple(documents[ref.document_id] for ref in selected_refs),
        context,
    )
    return (attribution_error,) if attribution_error is not None else ()


def _attribution_error(
    proposal: ClaimProposalV2,
    supporting_documents: tuple[SourceDocumentV2, ...],
    context: EvidenceContextV2,
) -> str | None:
    if proposal.claim_type in {"announcement", "opinion"} and (
        proposal.assertion_mode != "attributed" or proposal.attributed_to is None
    ):
        return "CLAIM_ATTRIBUTION_REQUIRED"
    if proposal.claim_type == "inference" and proposal.assertion_mode != "inference":
        return "CLAIM_INFERENCE_LABEL_REQUIRED"
    if proposal.assertion_mode == "attributed" and proposal.attributed_to is None:
        return "CLAIM_ATTRIBUTION_REQUIRED"
    if proposal.assertion_mode != "attributed" and proposal.attributed_to is not None:
        return "CLAIM_ATTRIBUTION_UNEXPECTED"
    if proposal.assertion_mode == "objective":
        selected_ids = {item.document_id for item in supporting_documents}
        family_ids = {
            family.family_id
            for family in context.source_families.families
            if set(family.member_document_ids).intersection(selected_ids)
        }
        confirmed = sum(
            family.independence_status == "confirmed"
            for family in context.source_families.families
            if family.family_id in family_ids
        )
        if confirmed == 0:
            return "CLAIM_INDEPENDENT_SUPPORT_REQUIRED"
        if supporting_documents and all(
            item.source_role == "primary" for item in supporting_documents
        ) and confirmed < 2:
            return "CLAIM_ATTRIBUTION_REQUIRED"
    return None


def _numbers(text: str) -> set[Decimal]:
    numbers: set[Decimal] = set()
    for raw in _NUMBER_PATTERN.findall(text):
        try:
            numbers.add(Decimal(raw.replace(",", "")))
        except InvalidOperation:
            continue
    return numbers


def _unit_supported(unit: str, text: str) -> bool:
    markers = _UNIT_MARKERS.get(unit.casefold(), (unit.casefold(),))
    lowered = text.casefold()
    return any(_marker_present(marker.casefold(), lowered) for marker in markers)


def _marker_present(marker: str, text: str) -> bool:
    if marker.isascii() and marker.isalpha():
        return re.search(rf"(?<![a-z]){re.escape(marker)}(?![a-z])", text) is not None
    return marker in text


def _claim_record(
    proposal: ClaimProposalV2,
    family_ids: tuple[str, ...],
    independent_support_count: int,
) -> ClaimRecordV2:
    value = "\x00".join(
        (
            proposal.event_id,
            proposal.claim_key,
            proposal.text,
            *proposal.support_refs,
        )
    )
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return ClaimRecordV2(
        claim_id=f"claim-{digest}",
        claim_key=proposal.claim_key,
        event_id=proposal.event_id,
        text=proposal.text,
        claim_type=proposal.claim_type,
        subject=proposal.subject,
        value_text=proposal.value_text,
        numeric_value=proposal.numeric_value,
        unit=proposal.unit,
        claim_time=proposal.claim_time,
        assertion_mode=proposal.assertion_mode,
        attributed_to=proposal.attributed_to,
        support_refs=proposal.support_refs,
        source_family_ids=family_ids,
        independent_support_count=independent_support_count,
    )


def evaluate_claim_recall(
    expected_claim_keys: tuple[str, ...],
    proposals: tuple[ClaimProposalV2, ...],
) -> ClaimRecallMetricsV2:
    if len(set(expected_claim_keys)) != len(expected_claim_keys):
        raise ValueError("EXPECTED_CLAIM_KEY_DUPLICATED")
    proposed = {item.claim_key for item in proposals}
    expected = set(expected_claim_keys)
    matched = expected.intersection(proposed)
    recall = len(matched) / len(expected) if expected else 1.0
    return ClaimRecallMetricsV2(
        recall=recall,
        expected_count=len(expected),
        proposed_count=len(proposed),
        missing_claim_keys=tuple(sorted(expected - proposed)),
        unexpected_claim_keys=tuple(sorted(proposed - expected)),
    )


class ConflictResolver:
    def classify(self, claims: tuple[ClaimRecordV2, ...]) -> ConflictSetV2:
        identifiers = [item.claim_id for item in claims]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("CONFLICT_CLAIM_DUPLICATED")
        groups: dict[
            tuple[str, str, str, str | None, datetime | None], list[ClaimRecordV2]
        ] = defaultdict(list)
        for claim in claims:
            groups[
                (
                    claim.event_id,
                    claim.claim_key,
                    claim.subject.casefold(),
                    claim.unit.casefold() if claim.unit is not None else None,
                    claim.claim_time,
                )
            ].append(claim)
        conflicts: list[ConflictGroupV2] = []
        conflicted_ids: set[str] = set()
        for key, members in sorted(groups.items(), key=lambda item: str(item[0])):
            values = {_claim_value(item) for item in members}
            if len(values) < 2:
                continue
            claim_ids = tuple(sorted(item.claim_id for item in members))
            digest = hashlib.sha256(
                "\x00".join((*map(str, key), *claim_ids)).encode("utf-8")
            ).hexdigest()[:24]
            conflicts.append(
                ConflictGroupV2(
                    conflict_id=f"conflict-{digest}",
                    claim_ids=claim_ids,
                    distinct_values=tuple(sorted(values)),
                )
            )
            conflicted_ids.update(claim_ids)
        updated = tuple(
            claim.model_copy(
                update={
                    "conflict_status": (
                        "unresolved" if claim.claim_id in conflicted_ids else "none"
                    )
                }
            )
            for claim in claims
        )
        return ConflictSetV2(
            claims=updated,
            groups=tuple(conflicts),
            certain_fact_claim_ids=tuple(
                sorted(
                    claim.claim_id
                    for claim in updated
                    if claim.claim_id not in conflicted_ids
                    and claim.assertion_mode == "objective"
                    and claim.independent_support_count > 0
                )
            ),
            attributed_dispute_claim_ids=tuple(
                sorted(
                    claim.claim_id
                    for claim in updated
                    if claim.claim_id in conflicted_ids
                    and claim.assertion_mode == "attributed"
                )
            ),
        )


def _claim_value(claim: ClaimRecordV2) -> str:
    if claim.numeric_value is not None:
        return format(claim.numeric_value.normalize(), "f")
    return (claim.value_text or claim.text).strip().casefold()


__all__ = [
    "CLAIMS_PROMPT_VERSION",
    "ClaimBatchV2",
    "ClaimDecisionPort",
    "ClaimExtractor",
    "ClaimProposalV2",
    "ClaimRecallMetricsV2",
    "ConflictGroupV2",
    "ConflictResolver",
    "ConflictSetV2",
    "RejectedClaimV2",
    "evaluate_claim_recall",
]
