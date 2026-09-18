"""R06 事件语义聚类与程序门禁测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from efficiency_platform_agent.capabilities.research.v2.clustering import (
    CLUSTER_PROMPT_VERSION,
    ClusterMemberJudgementV2,
    ClusterProposalV2,
    EventClusterer,
    evaluate_pairwise_clusters,
)
from efficiency_platform_agent.contracts.intent_v2 import (
    BudgetLeaseReferenceV2,
    OutputRequirementsV2,
    SourceConstraintsV2,
)
from efficiency_platform_agent.contracts.research_evidence_v2 import SourceDocumentV2
from efficiency_platform_agent.contracts.research_v2 import (
    CountPolicy,
    ResearchBriefV2,
    TrustedResearchContextV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow


def _brief() -> ResearchBriefV2:
    return ResearchBriefV2(
        trusted_context=TrustedResearchContextV2(
            tenant_id="tenant-1",
            run_id="run-1",
            task_id="task-1",
            budget_lease_id="lease-1",
        ),
        intent_revision=1,
        topic="AI 产品动态",
        entities=("Acme",),
        time_window=ResolvedTimeWindow(
            start=datetime(2026, 9, 1, tzinfo=UTC),
            end=datetime(2026, 10, 1, tzinfo=UTC),
            timezone="UTC",
            precision="month",
            original_text="2026-09",
            anchor=datetime(2026, 10, 1, tzinfo=UTC),
        ),
        source_constraints=SourceConstraintsV2(),
        count_policy=CountPolicy(mode="best_effort", target=5, minimum=1),
        output_requirements=OutputRequirementsV2(
            output_types=("digest",), language="zh-CN"
        ),
        quality_policy_id="quality-v2",
        policy_version="2026-09-17",
    )


def _document(index: int, **changes: object) -> SourceDocumentV2:
    values: dict[str, object] = {
        "document_id": f"doc-{index:02d}",
        "candidate_id": f"candidate-{index:02d}",
        "source_id": f"source-{index:02d}",
        "source_item_id": f"item-{index:02d}",
        "original_url": f"https://news{index}.example/acme-v2",
        "canonical_url": f"https://news{index}.example/acme-v2",
        "publisher_id": f"news{index}.example",
        "title": "Acme 发布 Model V2",
        "text": "Acme announced Model V2 today.",
        "content_hash": f"{index:064x}",
        "artifact_ref": f"inline:{index}",
        "discovered_via": "api",
        "content_scope": "full",
        "published_at": datetime(2026, 9, 15, 8, tzinfo=UTC),
        "published_timezone_known": True,
        "time_precision": "exact",
        "first_published_at": datetime(2026, 9, 15, 8, tzinfo=UTC),
        "extractor_version": "extractor/2",
        "source_role": "reporting",
    }
    values.update(changes)
    return SourceDocumentV2.model_validate(values)


def _proposal(
    brief: ResearchBriefV2,
    identifiers: tuple[str, ...],
    *,
    event_type: str = "product_release",
    versions: tuple[str | None, ...] | None = None,
) -> ClusterProposalV2:
    member_versions = versions or tuple("v2" for _ in identifiers)
    return ClusterProposalV2(
        proposal_id="proposal-" + "-".join(identifiers),
        brief_digest=brief.canonical_digest(),
        prompt_version=CLUSTER_PROMPT_VERSION,
        entity_names=("Acme",),
        members=tuple(
            ClusterMemberJudgementV2(
                document_id=document_id,
                event_type=event_type,
                product_version=version,
                semantic_equivalence="same_event",
            )
            for document_id, version in zip(identifiers, member_versions, strict=True)
        ),
        merge_basis=("same announcement",),
    )


class _Port:
    def __init__(self, proposals: tuple[ClusterProposalV2, ...]) -> None:
        self.proposals = proposals
        self.bucket_sizes: list[int] = []

    async def propose(self, bucket, brief, lease):
        self.bucket_sizes.append(len(bucket.documents))
        known = {item.document_id for item in bucket.documents}
        return tuple(
            proposal
            for proposal in self.proposals
            if any(member.document_id in known for member in proposal.members)
            or all(
                member.document_id.startswith("doc-unknown")
                for member in proposal.members
            )
        )


@pytest.mark.asyncio
async def test_ten_reposts_are_one_event() -> None:
    brief = _brief()
    documents = tuple(_document(index) for index in range(10))
    proposal = _proposal(brief, tuple(item.document_id for item in documents))

    result = await EventClusterer(_Port((proposal,))).cluster(
        documents, brief, BudgetLeaseReferenceV2(lease_id="lease-1", version=0)
    )

    assert result.event_count == 1
    assert result.events[0].member_document_ids == tuple(
        item.document_id for item in documents
    )


@pytest.mark.asyncio
async def test_release_incident_and_product_versions_are_not_hard_merged() -> None:
    brief = _brief()
    release = _document(1)
    incident = _document(2, title="Acme V2 服务事故", text="Acme V2 outage")
    release_proposal = _proposal(brief, (release.document_id,))
    incident_proposal = _proposal(
        brief, (incident.document_id,), event_type="service_incident"
    )
    result = await EventClusterer(_Port((release_proposal, incident_proposal))).cluster(
        (release, incident),
        brief,
        BudgetLeaseReferenceV2(lease_id="lease-1", version=0),
    )
    assert {event.event_type for event in result.events} == {
        "product_release",
        "service_incident",
    }

    conflicting = _proposal(
        brief,
        (release.document_id, incident.document_id),
        versions=("v1", "v2"),
    )
    split = await EventClusterer(_Port((conflicting,))).cluster(
        (release, incident),
        brief,
        BudgetLeaseReferenceV2(lease_id="lease-1", version=0),
    )
    assert split.event_count == 2
    assert all(event.cluster_confidence == "uncertain" for event in split.events)


@pytest.mark.asyncio
async def test_cross_language_same_event_can_merge_with_explicit_judgement() -> None:
    brief = _brief()
    chinese = _document(1)
    english = _document(
        2,
        title="Acme launches Model V2",
        text="The company launched Model V2.",
    )
    proposal = _proposal(brief, (chinese.document_id, english.document_id))

    result = await EventClusterer(_Port((proposal,))).cluster(
        (chinese, english),
        brief,
        BudgetLeaseReferenceV2(lease_id="lease-1", version=0),
    )

    assert result.event_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unknown", "duplicate"])
async def test_unknown_or_repeated_member_id_fails_closed(failure: str) -> None:
    brief = _brief()
    first = _document(1)
    second = _document(2)
    if failure == "unknown":
        proposals = (_proposal(brief, ("doc-unknown",)),)
        expected = "CLUSTER_MEMBER_UNKNOWN"
    else:
        proposals = (
            _proposal(brief, (first.document_id, second.document_id)),
            _proposal(brief, (second.document_id,)),
        )
        expected = "CLUSTER_MEMBER_DUPLICATED"

    with pytest.raises(ValueError, match=expected):
        await EventClusterer(_Port(proposals)).cluster(
            (first, second),
            brief,
            BudgetLeaseReferenceV2(lease_id="lease-1", version=0),
        )


@pytest.mark.asyncio
async def test_model_bucket_is_bounded_to_thirty_documents() -> None:
    brief = _brief()
    documents = tuple(_document(index) for index in range(61))
    port = _Port(())

    result = await EventClusterer(port).cluster(
        documents, brief, BudgetLeaseReferenceV2(lease_id="lease-1", version=0)
    )

    assert max(port.bucket_sizes) <= 30
    assert result.event_count == 61
    assert result.assigned_document_count == 61


@pytest.mark.asyncio
async def test_stale_proposal_splits_and_event_ids_ignore_input_order() -> None:
    brief = _brief()
    first = _document(1)
    second = _document(2)
    stale = _proposal(brief, (first.document_id, second.document_id)).model_copy(
        update={"prompt_version": "research.v2.cluster@0.9.0"}
    )

    forward = await EventClusterer(_Port((stale,))).cluster(
        (first, second),
        brief,
        BudgetLeaseReferenceV2(lease_id="lease-1", version=0),
    )
    reverse = await EventClusterer(_Port((stale,))).cluster(
        (second, first),
        brief,
        BudgetLeaseReferenceV2(lease_id="lease-1", version=0),
    )

    assert forward.event_count == 2
    assert forward.rejected_proposal_count == 1
    assert [item.event_id for item in forward.events] == [
        item.event_id for item in reverse.events
    ]


@pytest.mark.asyncio
async def test_pairwise_metrics_report_false_merge_instead_of_only_compression() -> None:
    brief = _brief()
    documents = tuple(_document(index) for index in range(3))
    merged = _proposal(brief, tuple(item.document_id for item in documents))
    predicted = await EventClusterer(_Port((merged,))).cluster(
        documents,
        brief,
        BudgetLeaseReferenceV2(lease_id="lease-1", version=0),
    )

    metrics = evaluate_pairwise_clusters(
        predicted,
        (("doc-00", "doc-01"), ("doc-02",)),
    )

    assert metrics.precision == pytest.approx(1 / 3)
    assert metrics.recall == 1.0
    assert metrics.false_positive_pairs == (
        ("doc-00", "doc-02"),
        ("doc-01", "doc-02"),
    )
