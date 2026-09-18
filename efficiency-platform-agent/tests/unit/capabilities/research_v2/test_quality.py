"""R08 H1-H6 单事件质量门禁测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from efficiency_platform_agent.capabilities.research.v2.claims import ConflictResolver
from efficiency_platform_agent.capabilities.research.v2.evidence import (
    build_evidence_ref,
)
from efficiency_platform_agent.capabilities.research.v2.filtering import FilterResultV2
from efficiency_platform_agent.capabilities.research.v2.quality import (
    CollectionCoverageV2,
    SourcePolicyDecisionV2,
    evaluate_quality,
)
from efficiency_platform_agent.contracts.intent_v2 import (
    OutputRequirementsV2,
    SourceConstraintsV2,
)
from efficiency_platform_agent.contracts.research_evidence_v2 import (
    ClaimRecordV2,
    EventClusterV2,
    SourceDocumentV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    CountPolicy,
    ResearchBriefV2,
    ResearchPolicySnapshotV2,
    TrustedResearchContextV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow


def _brief(mode: str = "exact", target: int = 1, minimum: int = 1):
    return ResearchBriefV2(
        trusted_context=TrustedResearchContextV2(
            tenant_id="tenant-1", run_id="run-1", task_id="task-1", budget_lease_id="lease-1"
        ),
        intent_revision=1,
        topic="AI",
        required_facets=("accuracy",),
        time_window=ResolvedTimeWindow(
            start=datetime(2026, 9, 15, tzinfo=UTC),
            end=datetime(2026, 9, 16, tzinfo=UTC),
            timezone="UTC",
            precision="day",
            original_text="2026-09-15",
            anchor=datetime(2026, 9, 16, tzinfo=UTC),
        ),
        source_constraints=SourceConstraintsV2(),
        count_policy=CountPolicy(mode=mode, target=target, minimum=minimum),
        output_requirements=OutputRequirementsV2(output_types=("digest",), language="zh-CN"),
        quality_policy_id="research-quality-v2",
        policy_version="2026-09-17",
    )


def _policy():
    return ResearchPolicySnapshotV2(
        quality_policy_id="research-quality-v2",
        policy_version="research-quality/2.0.0-offline",
    )


def _facts(*, content_scope="full", source_allowed=True):
    document = SourceDocumentV2(
        document_id="doc-1",
        candidate_id="candidate-1",
        source_id="source-1",
        source_item_id="item-1",
        original_url="https://official.example/result",
        canonical_url="https://official.example/result",
        publisher_id="official.example",
        ownership_group="official-group",
        title="Acme result",
        text="Acme reported accuracy 9 percent.",
        content_hash="a" * 64,
        artifact_ref="artifact:1",
        discovered_via="api",
        content_scope=content_scope,
        published_at=datetime(2026, 9, 15, tzinfo=UTC),
        published_timezone_known=True,
        time_precision="exact",
        extractor_version="extractor/2",
        source_role="reporting",
    )
    ref = build_evidence_ref(document, 0, len(document.text))
    event = EventClusterV2(
        event_id="event-1",
        event_type="measured_result",
        entity_names=("Acme",),
        event_time=datetime(2026, 9, 15, tzinfo=UTC),
        member_document_ids=(document.document_id,),
        representative_document_id=document.document_id,
        merge_basis=("same result",),
        cluster_confidence="confirmed",
    )
    claim = ClaimRecordV2(
        claim_id="claim-1",
        claim_key="accuracy",
        event_id=event.event_id,
        text="Acme accuracy was 9 percent.",
        claim_type="measured_result",
        subject="Acme",
        value_text="9",
        numeric_value=Decimal(9),
        unit="percent",
        claim_time=datetime(2026, 9, 15, tzinfo=UTC),
        assertion_mode="objective",
        support_refs=(ref.evidence_id,),
        source_family_ids=("family-1",),
        independent_support_count=1,
    )
    filters = FilterResultV2(
        accepted_document_ids=(document.document_id,),
        input_count=1,
        accepted_count=1,
        rejected_count=0,
        uncertain_count=0,
    )
    source = SourcePolicyDecisionV2(
        source_id=document.source_id,
        allowed=source_allowed,
        reason_codes=() if source_allowed else ("SOURCE_USE_FORBIDDEN",),
    )
    return document, ref, event, claim, filters, source


def _coverage(**changes):
    values = {
        "plan_complete": True,
        "attempt_count": 2,
        "critical_failure": False,
        "truncated": False,
        "historical_coverage": "complete",
    }
    values.update(changes)
    return CollectionCoverageV2.model_validate(values)


def _evaluate(brief, *, content_scope="full", source_allowed=True, coverage=None):
    document, ref, event, claim, filters, source = _facts(
        content_scope=content_scope, source_allowed=source_allowed
    )
    conflicts = ConflictResolver().classify((claim,))
    return evaluate_quality(
        brief,
        _policy(),
        (document,),
        (event,),
        (claim,),
        (ref,),
        filters,
        conflicts,
        (source,),
        coverage or _coverage(),
    )


def test_all_hard_gates_and_exact_one_are_complete() -> None:
    result = _evaluate(_brief())

    assert result.outcome == "COMPLETE"
    assert result.report.hard_gates_passed is True
    assert result.event_decisions[0].failed_gates == ()


def test_incomplete_content_and_disallowed_source_fail_h2_h6() -> None:
    summary = _evaluate(_brief(), content_scope="summary")
    forbidden = _evaluate(_brief(), source_allowed=False)

    assert summary.outcome == "FAILED"
    assert summary.event_decisions[0].failed_gates == ("H2",)
    assert forbidden.outcome == "FAILED"
    assert forbidden.event_decisions[0].failed_gates == ("H6",)


def test_unresolved_objective_conflict_fails_h5() -> None:
    document, ref, event, claim, filters, source = _facts()
    other = claim.model_copy(
        update={"claim_id": "claim-2", "value_text": "90", "numeric_value": Decimal(90)}
    )
    conflicts = ConflictResolver().classify((claim, other))

    result = evaluate_quality(
        _brief(), _policy(), (document,), (event,), (claim, other), (ref,), filters,
        conflicts, (source,), _coverage()
    )

    assert result.outcome == "FAILED"
    assert result.event_decisions[0].failed_gates == ("H5",)


def test_exact_shortage_is_partial_but_best_effort_below_target_is_complete() -> None:
    exact = _evaluate(_brief(mode="exact", target=3, minimum=1))
    best_effort = _evaluate(_brief(mode="best_effort", target=5, minimum=1))

    assert exact.outcome == "PARTIAL"
    assert exact.report.gaps[0].code == "COUNT_EXACT_UNMET"
    assert best_effort.outcome == "COMPLETE"


def test_fatal_integrity_failure_cannot_be_overridden_by_usable_event() -> None:
    result = _evaluate(_brief(), coverage=_coverage(critical_failure=True))

    assert result.outcome == "FAILED"
    assert result.report.hard_gates_passed is False
