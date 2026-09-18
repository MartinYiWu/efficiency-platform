from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from efficiency_platform_agent.capabilities.research.v2.evidence import (
    build_evidence_ref,
)
from efficiency_platform_agent.contracts.intent_v2 import (
    OutputRequirementsV2,
    SourceConstraintsV2,
)
from efficiency_platform_agent.contracts.research_evidence_v2 import (
    ClaimRecordV2,
    CoverageSnapshotV2,
    EventClusterV2,
    EvidenceSnapshotV2,
    SourceDocumentV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    CountPolicy,
    QualityGapV2,
    ResearchBriefV2,
    ResearchOutcomeV2,
    ResearchUsageV2,
    TrustedResearchContextV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow


def delivery_facts(target: int = 1):
    brief = ResearchBriefV2(
        trusted_context=TrustedResearchContextV2(
            tenant_id="t", run_id="r", task_id="x", budget_lease_id="lease"
        ),
        intent_revision=1,
        topic="AI",
        time_window=ResolvedTimeWindow(
            start=datetime(2026, 9, 15, tzinfo=UTC),
            end=datetime(2026, 9, 16, tzinfo=UTC),
            timezone="UTC",
            precision="day",
            original_text="2026-09-15",
            anchor=datetime(2026, 9, 16, tzinfo=UTC),
        ),
        source_constraints=SourceConstraintsV2(),
        count_policy=CountPolicy(mode="exact", target=target, minimum=1),
        output_requirements=OutputRequirementsV2(
            output_types=("digest",), language="zh-CN"
        ),
        quality_policy_id="quality-v2",
        policy_version="v2",
    )
    document = SourceDocumentV2(
        document_id="doc-1",
        candidate_id="candidate-1",
        source_id="source-1",
        source_item_id="item-1",
        original_url="https://official.example/result",
        canonical_url="https://official.example/result",
        publisher_id="official.example",
        title="Acme 离线验证结果",
        text="Acme reported accuracy 9 percent.",
        content_hash="a" * 64,
        artifact_ref="artifact:1",
        discovered_via="api",
        content_scope="full",
        published_at=datetime(2026, 9, 15, tzinfo=UTC),
        published_timezone_known=True,
        time_precision="exact",
        extractor_version="extractor/2",
        source_role="primary",
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
    snapshot = EvidenceSnapshotV2(
        snapshot_id="snapshot-1",
        brief_digest=brief.canonical_digest(),
        documents=(document,),
        events=(event,),
        claims=(claim,),
        evidence_refs=(ref,),
        coverage=CoverageSnapshotV2(
            required_facets=(),
            covered_facets=(),
            missing_facets=(),
            historical_coverage="complete",
        ),
    )
    return brief, snapshot, document, event, claim, ref


def research_outcome(brief, *, partial: bool = False):
    gaps = (
        (
            QualityGapV2(
                gap_id="gap-count",
                requirement_id="count_policy",
                code="COUNT_EXACT_UNMET",
                detail="still missing one",
                recoverable=True,
            ),
        )
        if partial
        else ()
    )
    return ResearchOutcomeV2(
        outcome="PARTIAL" if partial else "COMPLETE",
        usable_event_ids=("event-1",),
        evidence_ids=(),
        gaps=gaps,
        stop_reason="BUDGET_LIMIT" if partial else "QUALITY_MET",
        usage=ResearchUsageV2(source_requests=1, model_calls=0, downloaded_bytes=100),
    )
