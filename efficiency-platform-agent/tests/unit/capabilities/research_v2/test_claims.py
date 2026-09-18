"""R07 Claim 数值、归属与来源家族门禁测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from efficiency_platform_agent.capabilities.research.v2.claims import (
    CLAIMS_PROMPT_VERSION,
    ClaimExtractor,
    ClaimProposalV2,
    evaluate_claim_recall,
)
from efficiency_platform_agent.capabilities.research.v2.evidence import (
    EvidenceContextV2,
    build_evidence_ref,
)
from efficiency_platform_agent.capabilities.research.v2.source_families import (
    SourceFamilyResolver,
)
from efficiency_platform_agent.contracts.intent_v2 import BudgetLeaseReferenceV2
from efficiency_platform_agent.contracts.research_evidence_v2 import (
    EventClusterV2,
    SourceDocumentV2,
)


def _document(index: int = 1, **changes: object) -> SourceDocumentV2:
    values: dict[str, object] = {
        "document_id": f"doc-{index}",
        "candidate_id": f"candidate-{index}",
        "source_id": f"source-{index}",
        "source_item_id": f"item-{index}",
        "original_url": f"https://official{index}.example/release",
        "canonical_url": f"https://official{index}.example/release",
        "publisher_id": f"official{index}.example",
        "title": "Acme 测试结果",
        "text": "Acme 表示测试准确率为 9%。",
        "content_hash": f"{index:064x}",
        "artifact_ref": f"artifact:doc-{index}",
        "discovered_via": "public_page",
        "content_scope": "full",
        "published_at": datetime(2026, 9, 15, tzinfo=UTC),
        "published_timezone_known": True,
        "time_precision": "exact",
        "extractor_version": "extractor/2",
        "source_role": "primary",
    }
    values.update(changes)
    return SourceDocumentV2.model_validate(values)


def _event(document_ids: tuple[str, ...] = ("doc-1",)) -> EventClusterV2:
    return EventClusterV2(
        event_id="event-1",
        event_type="measured_result",
        entity_names=("Acme",),
        event_time=datetime(2026, 9, 15, tzinfo=UTC),
        member_document_ids=document_ids,
        representative_document_id=document_ids[0],
        merge_basis=("same report",),
        cluster_confidence="confirmed",
    )


def _context(documents: tuple[SourceDocumentV2, ...]) -> EvidenceContextV2:
    refs = []
    for document in documents:
        refs.append(build_evidence_ref(document, 0, len(document.text)))
    return EvidenceContextV2(
        brief_digest="b" * 64,
        documents=documents,
        evidence_refs=tuple(refs),
        source_families=SourceFamilyResolver().resolve(documents),
    )


def _proposal(
    context: EvidenceContextV2,
    **changes: object,
) -> ClaimProposalV2:
    values: dict[str, object] = {
        "proposal_id": "proposal-1",
        "claim_key": "accuracy",
        "brief_digest": context.brief_digest,
        "prompt_version": CLAIMS_PROMPT_VERSION,
        "event_id": "event-1",
        "text": "Acme 表示准确率为 9%。",
        "claim_type": "announcement",
        "subject": "Acme",
        "value_text": "9",
        "numeric_value": Decimal(9),
        "unit": "percent",
        "claim_time": datetime(2026, 9, 15, tzinfo=UTC),
        "assertion_mode": "attributed",
        "attributed_to": "Acme",
        "support_refs": (context.evidence_refs[0].evidence_id,),
    }
    values.update(changes)
    return ClaimProposalV2.model_validate(values)


class _Port:
    def __init__(self, proposals: tuple[ClaimProposalV2, ...]) -> None:
        self.proposals = proposals

    async def propose(self, events, evidence_context, lease):
        return self.proposals


@pytest.mark.asyncio
async def test_source_nine_cannot_support_claim_ninety() -> None:
    document = _document()
    context = _context((document,))
    proposal = _proposal(
        context,
        text="Acme 表示准确率为 90%。",
        value_text="90",
        numeric_value=Decimal(90),
    )

    result = await ClaimExtractor(_Port((proposal,))).extract(
        (_event(),),
        context,
        BudgetLeaseReferenceV2(lease_id="lease-1", version=0),
    )

    assert result.accepted == ()
    assert result.rejected[0].reason_codes == ("CLAIM_NUMBER_UNSUPPORTED",)


@pytest.mark.asyncio
async def test_unit_change_and_unknown_evidence_are_rejected() -> None:
    context = _context((_document(),))
    changed_unit = _proposal(context, unit="seconds")
    unknown_ref = _proposal(context, support_refs=("evidence-unknown",))

    unit_result = await ClaimExtractor(_Port((changed_unit,))).extract(
        (_event(),), context, BudgetLeaseReferenceV2(lease_id="lease-1", version=0)
    )
    ref_result = await ClaimExtractor(_Port((unknown_ref,))).extract(
        (_event(),), context, BudgetLeaseReferenceV2(lease_id="lease-1", version=0)
    )

    assert unit_result.rejected[0].reason_codes == ("CLAIM_UNIT_UNSUPPORTED",)
    assert ref_result.rejected[0].reason_codes == ("CLAIM_EVIDENCE_UNKNOWN",)


@pytest.mark.asyncio
async def test_value_text_cannot_disagree_with_bound_numeric_value() -> None:
    context = _context((_document(),))
    inconsistent = _proposal(
        context,
        text="Acme 表示准确率为 90%。",
        value_text="90",
        numeric_value=Decimal(9),
    )

    result = await ClaimExtractor(_Port((inconsistent,))).extract(
        (_event(),), context, BudgetLeaseReferenceV2(lease_id="lease-1", version=0)
    )

    assert result.rejected[0].reason_codes == ("CLAIM_VALUE_INCONSISTENT",)


@pytest.mark.asyncio
async def test_official_announcement_must_remain_attributed() -> None:
    context = _context((_document(),))
    objective = _proposal(
        context,
        claim_type="reported_fact",
        assertion_mode="objective",
        attributed_to=None,
    )
    attributed = _proposal(context)

    rejected = await ClaimExtractor(_Port((objective,))).extract(
        (_event(),), context, BudgetLeaseReferenceV2(lease_id="lease-1", version=0)
    )
    accepted = await ClaimExtractor(_Port((attributed,))).extract(
        (_event(),), context, BudgetLeaseReferenceV2(lease_id="lease-1", version=0)
    )

    assert rejected.rejected[0].reason_codes == ("CLAIM_ATTRIBUTION_REQUIRED",)
    assert accepted.accepted[0].assertion_mode == "attributed"
    assert accepted.accepted[0].attributed_to == "Acme"


@pytest.mark.asyncio
async def test_ten_identical_reposts_do_not_become_ten_independent_supports() -> None:
    documents = tuple(
        _document(
            index,
            source_role="reporting",
            content_hash="a" * 64,
            text="Acme 表示测试准确率为 9%。",
        )
        for index in range(1, 11)
    )
    context = _context(documents)
    proposal = _proposal(
        context,
        support_refs=tuple(item.evidence_id for item in context.evidence_refs),
    )

    result = await ClaimExtractor(_Port((proposal,))).extract(
        (_event(tuple(item.document_id for item in documents)),),
        context,
        BudgetLeaseReferenceV2(lease_id="lease-1", version=0),
    )

    assert result.accepted[0].source_family_ids == (
        context.source_families.families[0].family_id,
    )
    assert result.accepted[0].independent_support_count == 0


def test_manual_expected_claim_keys_expose_model_omission() -> None:
    context = _context((_document(),))
    metrics = evaluate_claim_recall(
        ("accuracy", "latency"),
        (_proposal(context),),
    )

    assert metrics.recall == 0.5
    assert metrics.missing_claim_keys == ("latency",)
