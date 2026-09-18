"""R10 编造、断链、重复、数量、范围和状态门禁。"""

import pytest

from efficiency_platform_agent.capabilities.research.v2.output_verifier import (
    OutputVerificationPolicyV2,
    OutputVerifier,
)
from efficiency_platform_agent.contracts.research_v2 import DeliveryDraftV2
from tests.unit.capabilities.research_v2._delivery_support import delivery_facts


def _draft(brief, claim, ref, **changes):
    values = {
        "draft_id": "draft-1",
        "brief_digest": brief.canonical_digest(),
        "content": f"{claim.text} [evidence:{ref.evidence_id}]",
        "event_ids": ("event-1",),
        "claim_ids": (claim.claim_id,),
        "evidence_ids": (ref.evidence_id,),
        "declared_outcome": "PARTIAL",
        "output_type": "digest",
    }
    values.update(changes)
    return DeliveryDraftV2.model_validate(values)


@pytest.mark.asyncio
async def test_verified_draft_is_accepted() -> None:
    brief, snapshot, _, _, claim, ref = delivery_facts()
    decision = await OutputVerifier().verify(
        _draft(brief, claim, ref),
        brief,
        snapshot,
        OutputVerificationPolicyV2(expected_outcome="PARTIAL"),
    )
    assert decision.outcome == "ACCEPT"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        (
            {"content": "Acme accuracy was 90 percent. https://fake.example"},
            "OUTPUT_MODEL_URL_FORBIDDEN",
        ),
        (
            {"content": "Acme accuracy was 90 percent."},
            "OUTPUT_CLAIM_UNSUPPORTED",
        ),
        ({"evidence_ids": ("evidence-missing",)}, "OUTPUT_CITATION_BROKEN"),
        ({"event_ids": ("event-1", "event-1")}, "OUTPUT_EVENT_DUPLICATED"),
        ({"exhaustive_scope_claimed": True}, "OUTPUT_EXHAUSTIVE_CLAIM_FORBIDDEN"),
        ({"declared_outcome": "COMPLETE"}, "OUTPUT_STATUS_ESCALATED"),
    ],
)
async def test_unsafe_model_output_is_revised(changes, reason) -> None:
    brief, snapshot, _, _, claim, ref = delivery_facts()
    decision = await OutputVerifier().verify(
        _draft(brief, claim, ref, **changes),
        brief,
        snapshot,
        OutputVerificationPolicyV2(expected_outcome="PARTIAL"),
    )
    assert decision.outcome == "REVISE"
    assert reason in decision.reason_codes


@pytest.mark.asyncio
async def test_second_failed_repair_is_rejected() -> None:
    brief, snapshot, _, _, claim, ref = delivery_facts()
    decision = await OutputVerifier().verify(
        _draft(brief, claim, ref, content="fabricated", repair_attempt=1),
        brief,
        snapshot,
        OutputVerificationPolicyV2(expected_outcome="PARTIAL"),
    )
    assert decision.outcome == "REJECT"
    assert decision.unsupported_claim_ids == (claim.claim_id,)


@pytest.mark.asyncio
async def test_complete_exact_shortfall_requests_recollection() -> None:
    brief, snapshot, _, _, claim, ref = delivery_facts(target=2)
    decision = await OutputVerifier().verify(
        _draft(brief, claim, ref, declared_outcome="COMPLETE"),
        brief,
        snapshot,
        OutputVerificationPolicyV2(expected_outcome="COMPLETE"),
    )
    assert decision.outcome == "RECOLLECT"
    assert "OUTPUT_EXACT_COUNT_UNMET" in decision.reason_codes
