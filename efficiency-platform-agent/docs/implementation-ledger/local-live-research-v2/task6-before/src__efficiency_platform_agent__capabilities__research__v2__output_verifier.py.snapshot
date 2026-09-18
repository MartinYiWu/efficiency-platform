"""对模型草稿执行确定性引用、事实、数量与范围核验。"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from efficiency_platform_agent.contracts.research_evidence_v2 import EvidenceSnapshotV2
from efficiency_platform_agent.contracts.research_v2 import (
    DeliveryDraftV2,
    OutputDecisionV2,
    ResearchBriefV2,
)

_URL = re.compile(r"https?://[^\s)\]}]+", re.IGNORECASE)
_EXHAUSTIVE = ("全网", "所有来源", "全部公开信息", "穷尽")


class OutputVerificationPolicyV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_outcome: str = Field(min_length=1, max_length=32)
    require_every_usable_claim: bool = True
    citations_required: bool = True


class OutputVerifier:
    async def verify(
        self,
        draft: DeliveryDraftV2,
        brief: ResearchBriefV2,
        evidence_snapshot: EvidenceSnapshotV2,
        policy: OutputVerificationPolicyV2,
    ) -> OutputDecisionV2:
        reasons: list[str] = []
        unsupported: set[str] = set()
        if draft.brief_digest != brief.canonical_digest() or (
            evidence_snapshot.brief_digest != draft.brief_digest
        ):
            return OutputDecisionV2(
                outcome="REJECT", reason_codes=("OUTPUT_SCOPE_MISMATCH",)
            )
        if draft.declared_outcome != policy.expected_outcome:
            reasons.append("OUTPUT_STATUS_ESCALATED")
        if draft.output_type not in brief.output_requirements.output_types:
            reasons.append("OUTPUT_FORMAT_UNREQUESTED")
        if draft.exhaustive_scope_claimed or any(
            marker in draft.content for marker in _EXHAUSTIVE
        ):
            reasons.append("OUTPUT_EXHAUSTIVE_CLAIM_FORBIDDEN")
        if _URL.search(draft.content):
            reasons.append("OUTPUT_MODEL_URL_FORBIDDEN")
        known_events = {item.event_id for item in evidence_snapshot.events}
        if len(set(draft.event_ids)) != len(draft.event_ids):
            reasons.append("OUTPUT_EVENT_DUPLICATED")
        if not set(draft.event_ids).issubset(known_events):
            reasons.append("OUTPUT_EVENT_UNKNOWN")
        if (
            brief.count_policy.mode == "exact"
            and policy.expected_outcome == "COMPLETE"
            and len(draft.event_ids) < brief.count_policy.target
        ):
            reasons.append("OUTPUT_EXACT_COUNT_UNMET")
        claims = {item.claim_id: item for item in evidence_snapshot.claims}
        refs = {item.evidence_id for item in evidence_snapshot.evidence_refs}
        for claim_id in draft.claim_ids:
            claim = claims.get(claim_id)
            if claim is None or claim.event_id not in draft.event_ids:
                unsupported.add(claim_id)
                continue
            if claim.text not in draft.content:
                unsupported.add(claim_id)
            if not set(claim.support_refs).issubset(set(draft.evidence_ids)):
                unsupported.add(claim_id)
            if policy.citations_required and any(
                f"[evidence:{ref_id}]" not in draft.content
                for ref_id in claim.support_refs
            ):
                unsupported.add(claim_id)
        if not set(draft.evidence_ids).issubset(refs):
            reasons.append("OUTPUT_CITATION_BROKEN")
        expected_claims = {
            item.claim_id
            for item in evidence_snapshot.claims
            if item.event_id in draft.event_ids
            and not (
                item.assertion_mode == "objective"
                and item.conflict_status == "unresolved"
            )
        }
        if policy.require_every_usable_claim and not expected_claims.issubset(
            set(draft.claim_ids)
        ):
            reasons.append("OUTPUT_FACT_OMITTED")
        if unsupported:
            reasons.append("OUTPUT_CLAIM_UNSUPPORTED")
        if not reasons:
            return OutputDecisionV2(outcome="ACCEPT")
        if draft.repair_attempt >= 1:
            return OutputDecisionV2(
                outcome="REJECT",
                reason_codes=tuple(dict.fromkeys(reasons)),
                unsupported_claim_ids=tuple(sorted(unsupported)),
            )
        recollect = "OUTPUT_EXACT_COUNT_UNMET" in reasons
        return OutputDecisionV2(
            outcome="RECOLLECT" if recollect else "REVISE",
            reason_codes=tuple(dict.fromkeys(reasons)),
            unsupported_claim_ids=tuple(sorted(unsupported)),
        )


__all__ = ["OutputVerificationPolicyV2", "OutputVerifier"]
