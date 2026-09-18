"""R07 Claim 冲突保留测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from efficiency_platform_agent.capabilities.research.v2.claims import ConflictResolver
from efficiency_platform_agent.contracts.research_evidence_v2 import ClaimRecordV2


def _claim(
    claim_id: str,
    value: str,
    family_id: str,
    *,
    assertion_mode: str = "objective",
    independent_support_count: int = 1,
) -> ClaimRecordV2:
    return ClaimRecordV2(
        claim_id=claim_id,
        claim_key="accuracy",
        event_id="event-1",
        text=f"Acme accuracy {value}%",
        claim_type="reported_fact",
        subject="Acme",
        value_text=value,
        numeric_value=Decimal(value),
        unit="percent",
        claim_time=datetime(2026, 9, 15, tzinfo=UTC),
        assertion_mode=assertion_mode,
        attributed_to="Publisher" if assertion_mode == "attributed" else None,
        support_refs=(f"evidence-{claim_id}",),
        source_family_ids=(family_id,),
        independent_support_count=independent_support_count,
    )


def test_conflicting_values_are_preserved_and_not_certain_facts() -> None:
    first = _claim("claim-1", "9", "family-1")
    second = _claim("claim-2", "90", "family-2")

    result = ConflictResolver().classify((first, second))

    assert result.groups[0].status == "unresolved"
    assert result.groups[0].claim_ids == ("claim-1", "claim-2")
    assert result.certain_fact_claim_ids == ()
    assert all(item.conflict_status == "unresolved" for item in result.claims)


def test_attributed_dispute_can_be_delivered_but_not_as_certain_fact() -> None:
    first = _claim("claim-1", "9", "family-1", assertion_mode="attributed")
    second = _claim("claim-2", "90", "family-2", assertion_mode="attributed")

    result = ConflictResolver().classify((first, second))

    assert result.certain_fact_claim_ids == ()
    assert result.attributed_dispute_claim_ids == ("claim-1", "claim-2")


def test_same_family_repetition_does_not_create_conflict_or_votes() -> None:
    first = _claim("claim-1", "9", "family-wire", independent_support_count=0)
    second = _claim("claim-2", "9", "family-wire", independent_support_count=0)

    result = ConflictResolver().classify((first, second))

    assert result.groups == ()
    assert result.certain_fact_claim_ids == ()


def test_different_atomic_predicates_with_same_unit_are_not_conflicts() -> None:
    accuracy = _claim("claim-1", "9", "family-1")
    latency = _claim("claim-2", "90", "family-2").model_copy(
        update={"claim_key": "latency"}
    )

    result = ConflictResolver().classify((accuracy, latency))

    assert result.groups == ()
    assert result.certain_fact_claim_ids == ("claim-1", "claim-2")
