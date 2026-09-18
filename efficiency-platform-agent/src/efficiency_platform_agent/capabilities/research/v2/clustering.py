"""模型提案、程序裁决的有界事件聚类。"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from itertools import combinations
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.contracts.intent_v2 import BudgetLeaseReferenceV2
from efficiency_platform_agent.contracts.research_evidence_v2 import (
    EventClusterV2,
    SourceDocumentV2,
)
from efficiency_platform_agent.contracts.research_v2 import ResearchBriefV2

CLUSTER_PROMPT_VERSION = "research.v2.cluster@1.0.0"
_VERSION_PATTERN = re.compile(r"(?i)(?<![\w])v\d+(?:\.\d+)*(?![\w])")
_MAX_BUCKET_SIZE = 30
_NEARBY = timedelta(days=2)


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ClusterMemberJudgementV2(_FrozenContract):
    document_id: str = Field(min_length=1, max_length=128)
    event_type: str = Field(min_length=1, max_length=128)
    product_version: str | None = Field(default=None, min_length=1, max_length=128)
    semantic_equivalence: Literal["same_event", "different_event", "uncertain"]


class ClusterProposalV2(_FrozenContract):
    proposal_id: str = Field(min_length=1, max_length=512)
    brief_digest: str = Field(min_length=64, max_length=64)
    prompt_version: str = Field(min_length=1, max_length=128)
    entity_names: tuple[str, ...] = Field(default=(), max_length=64)
    members: tuple[ClusterMemberJudgementV2, ...] = Field(
        min_length=1, max_length=_MAX_BUCKET_SIZE
    )
    merge_basis: tuple[str, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_members(self) -> ClusterProposalV2:
        identifiers = [item.document_id for item in self.members]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("CLUSTER_PROPOSAL_MEMBER_DUPLICATED")
        if len(set(self.entity_names)) != len(self.entity_names):
            raise ValueError("CLUSTER_ENTITY_DUPLICATED")
        return self


class ClusterBucketV2(_FrozenContract):
    bucket_id: str = Field(min_length=1, max_length=128)
    documents: tuple[SourceDocumentV2, ...] = Field(
        min_length=1, max_length=_MAX_BUCKET_SIZE
    )


class EventClustersV2(_FrozenContract):
    events: tuple[EventClusterV2, ...] = Field(default=(), max_length=2_000)
    input_document_count: int = Field(ge=0)
    assigned_document_count: int = Field(ge=0)
    event_count: int = Field(ge=0)
    rejected_proposal_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_conservation(self) -> EventClustersV2:
        members = [
            document_id
            for event in self.events
            for document_id in event.member_document_ids
        ]
        if (
            self.event_count != len(self.events)
            or self.assigned_document_count != len(members)
            or self.input_document_count != self.assigned_document_count
            or len(set(members)) != len(members)
        ):
            raise ValueError("EVENT_CLUSTER_COUNT_INVALID")
        return self


class PairwiseClusterMetricsV2(_FrozenContract):
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    predicted_pair_count: int = Field(ge=0)
    gold_pair_count: int = Field(ge=0)
    false_positive_pairs: tuple[tuple[str, str], ...] = Field(
        default=(), max_length=100_000
    )
    false_negative_pairs: tuple[tuple[str, str], ...] = Field(
        default=(), max_length=100_000
    )


@runtime_checkable
class EventClusterDecisionPort(Protocol):
    async def propose(
        self,
        bucket: ClusterBucketV2,
        brief: ResearchBriefV2,
        lease: BudgetLeaseReferenceV2,
    ) -> tuple[ClusterProposalV2, ...]: ...


class EventClusterer:
    """按有界确定性桶调用语义端口，并严格验证返回成员关系。"""

    def __init__(self, decision_port: EventClusterDecisionPort) -> None:
        if not isinstance(decision_port, EventClusterDecisionPort):
            raise TypeError("decision_port 必须实现 EventClusterDecisionPort")
        self._decision_port = decision_port

    async def cluster(
        self,
        documents: tuple[SourceDocumentV2, ...],
        brief: ResearchBriefV2,
        lease: BudgetLeaseReferenceV2,
    ) -> EventClustersV2:
        if not isinstance(brief, ResearchBriefV2):
            raise TypeError("brief 类型无效")
        if not isinstance(lease, BudgetLeaseReferenceV2):
            raise TypeError("lease 类型无效")
        by_id = {item.document_id: item for item in documents}
        if len(by_id) != len(documents):
            raise ValueError("CLUSTER_DOCUMENT_DUPLICATED")

        accepted_events: list[EventClusterV2] = []
        seen_members: set[str] = set()
        rejected_count = 0
        for bucket in _build_buckets(documents, brief):
            proposals = await self._decision_port.propose(bucket, brief, lease)
            if not isinstance(proposals, tuple) or any(
                not isinstance(item, ClusterProposalV2) for item in proposals
            ):
                raise TypeError("CLUSTER_PROPOSALS_INVALID")
            bucket_ids = {item.document_id for item in bucket.documents}
            for proposal in proposals:
                proposal_ids = {item.document_id for item in proposal.members}
                unknown = proposal_ids - set(by_id)
                if unknown:
                    raise ValueError("CLUSTER_MEMBER_UNKNOWN")
                if not proposal_ids.issubset(bucket_ids):
                    raise ValueError("CLUSTER_MEMBER_OUTSIDE_BUCKET")
                if seen_members.intersection(proposal_ids):
                    raise ValueError("CLUSTER_MEMBER_DUPLICATED")
                seen_members.update(proposal_ids)
                if not _proposal_is_safe(proposal, brief):
                    rejected_count += 1
                    continue
                accepted_events.append(
                    _event_from_proposal(proposal, by_id, brief)
                )

        assigned = {
            document_id
            for event in accepted_events
            for document_id in event.member_document_ids
        }
        for document in sorted(documents, key=lambda item: item.document_id):
            if document.document_id not in assigned:
                accepted_events.append(_singleton_event(document, brief))
        events = tuple(sorted(accepted_events, key=lambda item: item.event_id))
        return EventClustersV2(
            events=events,
            input_document_count=len(documents),
            assigned_document_count=sum(
                len(item.member_document_ids) for item in events
            ),
            event_count=len(events),
            rejected_proposal_count=rejected_count,
        )


def evaluate_pairwise_clusters(
    predicted: EventClustersV2,
    gold_clusters: tuple[tuple[str, ...], ...],
) -> PairwiseClusterMetricsV2:
    """以同一文档全集计算 pairwise precision/recall 并列出误合并。"""

    predicted_members = {
        member for event in predicted.events for member in event.member_document_ids
    }
    gold_members = [member for cluster in gold_clusters for member in cluster]
    if (
        len(set(gold_members)) != len(gold_members)
        or set(gold_members) != predicted_members
    ):
        raise ValueError("CLUSTER_EVALUATION_UNIVERSE_INVALID")
    predicted_pairs = _cluster_pairs(
        tuple(event.member_document_ids for event in predicted.events)
    )
    gold_pairs = _cluster_pairs(gold_clusters)
    correct = predicted_pairs.intersection(gold_pairs)
    false_positive = tuple(sorted(predicted_pairs - gold_pairs))
    false_negative = tuple(sorted(gold_pairs - predicted_pairs))
    precision = len(correct) / len(predicted_pairs) if predicted_pairs else 1.0
    recall = len(correct) / len(gold_pairs) if gold_pairs else 1.0
    return PairwiseClusterMetricsV2(
        precision=precision,
        recall=recall,
        predicted_pair_count=len(predicted_pairs),
        gold_pair_count=len(gold_pairs),
        false_positive_pairs=false_positive,
        false_negative_pairs=false_negative,
    )


def _cluster_pairs(
    clusters: tuple[tuple[str, ...], ...],
) -> set[tuple[str, str]]:
    return {
        pair
        for cluster in clusters
        for pair in combinations(tuple(sorted(cluster)), 2)
    }


def _proposal_is_safe(
    proposal: ClusterProposalV2,
    brief: ResearchBriefV2,
) -> bool:
    event_types = {item.event_type for item in proposal.members}
    versions = {item.product_version for item in proposal.members}
    return (
        proposal.brief_digest == brief.canonical_digest()
        and proposal.prompt_version == CLUSTER_PROMPT_VERSION
        and all(
            item.semantic_equivalence == "same_event" for item in proposal.members
        )
        and len(event_types) == 1
        and len(versions) == 1
    )


def _event_from_proposal(
    proposal: ClusterProposalV2,
    by_id: dict[str, SourceDocumentV2],
    brief: ResearchBriefV2,
) -> EventClusterV2:
    identifiers = tuple(sorted(item.document_id for item in proposal.members))
    documents = tuple(by_id[item] for item in identifiers)
    event_type = proposal.members[0].event_type
    version = proposal.members[0].product_version
    return EventClusterV2(
        event_id=_event_id(brief, identifiers, event_type, version),
        event_type=event_type,
        entity_names=tuple(sorted(proposal.entity_names)),
        event_time=_event_time(documents),
        product_version=version,
        member_document_ids=identifiers,
        representative_document_id=_representative(documents).document_id,
        merge_basis=proposal.merge_basis,
        cluster_confidence="confirmed",
    )


def _singleton_event(
    document: SourceDocumentV2,
    brief: ResearchBriefV2,
) -> EventClusterV2:
    versions = _versions(document)
    version = versions[0] if len(versions) == 1 else None
    identifier = (document.document_id,)
    return EventClusterV2(
        event_id=_event_id(brief, identifier, "unknown", version),
        event_type="unknown",
        entity_names=_entities(document, brief),
        event_time=_document_time(document),
        product_version=version,
        member_document_ids=identifier,
        representative_document_id=document.document_id,
        merge_basis=("singleton_uncertain",),
        cluster_confidence="uncertain",
    )


def _event_id(
    brief: ResearchBriefV2,
    identifiers: tuple[str, ...],
    event_type: str,
    version: str | None,
) -> str:
    value = "\x00".join(
        (brief.canonical_digest(), event_type, version or "", *identifiers)
    )
    return "event-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _build_buckets(
    documents: tuple[SourceDocumentV2, ...],
    brief: ResearchBriefV2,
) -> tuple[ClusterBucketV2, ...]:
    grouped: dict[
        tuple[tuple[str, ...], tuple[str, ...]], list[SourceDocumentV2]
    ] = defaultdict(list)
    for document in documents:
        grouped[(_entities(document, brief), _versions(document))].append(document)
    buckets: list[ClusterBucketV2] = []
    sequence = 0
    for _, members in sorted(grouped.items(), key=lambda item: item[0]):
        ordered = sorted(
            members,
            key=lambda item: (
                _document_time(item) is None,
                _document_time(item) or datetime.max.replace(tzinfo=UTC),
                item.document_id,
            ),
        )
        nearby_groups: list[list[SourceDocumentV2]] = []
        for document in ordered:
            if not nearby_groups or _starts_new_time_group(
                nearby_groups[-1][-1], document
            ):
                nearby_groups.append([document])
            else:
                nearby_groups[-1].append(document)
        for nearby in nearby_groups:
            for offset in range(0, len(nearby), _MAX_BUCKET_SIZE):
                chunk = tuple(nearby[offset : offset + _MAX_BUCKET_SIZE])
                buckets.append(
                    ClusterBucketV2(
                        bucket_id=f"bucket-{sequence:06d}", documents=chunk
                    )
                )
                sequence += 1
    return tuple(buckets)


def _starts_new_time_group(
    previous: SourceDocumentV2,
    current: SourceDocumentV2,
) -> bool:
    previous_time = _document_time(previous)
    current_time = _document_time(current)
    if previous_time is None or current_time is None:
        return previous_time is not current_time
    return current_time - previous_time > _NEARBY


def _entities(
    document: SourceDocumentV2,
    brief: ResearchBriefV2,
) -> tuple[str, ...]:
    text = f"{document.title}\n{document.text}".casefold()
    return tuple(sorted(entity for entity in brief.entities if entity.casefold() in text))


def _versions(document: SourceDocumentV2) -> tuple[str, ...]:
    values = _VERSION_PATTERN.findall(f"{document.title}\n{document.text}")
    return tuple(sorted({item.casefold() for item in values}))


def _document_time(document: SourceDocumentV2) -> datetime | None:
    return (
        document.event_at
        or document.first_published_at
        or document.published_at
        or document.updated_at
    )


def _event_time(documents: tuple[SourceDocumentV2, ...]) -> datetime | None:
    values = [value for item in documents if (value := _document_time(item)) is not None]
    return min(values) if values else None


def _representative(
    documents: tuple[SourceDocumentV2, ...],
) -> SourceDocumentV2:
    return min(
        documents,
        key=lambda item: (
            item.source_role != "primary",
            _document_time(item) is None,
            _document_time(item) or datetime.max.replace(tzinfo=UTC),
            item.document_id,
        ),
    )


__all__ = [
    "CLUSTER_PROMPT_VERSION",
    "ClusterBucketV2",
    "ClusterMemberJudgementV2",
    "ClusterProposalV2",
    "EventClusterDecisionPort",
    "EventClusterer",
    "EventClustersV2",
    "PairwiseClusterMetricsV2",
    "evaluate_pairwise_clusters",
]
