"""R05 严格时间、条件和语义过滤测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from efficiency_platform_agent.capabilities.research.v2.filtering import (
    RELEVANCE_PROMPT_VERSION,
    SemanticRelevanceDecisionV2,
    filter_documents,
)
from efficiency_platform_agent.contracts.intent_v2 import (
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


def _brief(**changes: object) -> ResearchBriefV2:
    values: dict[str, object] = {
        "trusted_context": TrustedResearchContextV2(
            tenant_id="tenant-1",
            run_id="run-1",
            task_id="task-1",
            budget_lease_id="lease-1",
        ),
        "intent_revision": 1,
        "topic": "人工智能行业动态",
        "time_window": ResolvedTimeWindow(
            start=datetime(2026, 9, 15, tzinfo=UTC),
            end=datetime(2026, 9, 16, tzinfo=UTC),
            timezone="UTC",
            precision="day",
            original_text="2026-09-15",
            anchor=datetime(2026, 9, 16, tzinfo=UTC),
        ),
        "source_constraints": SourceConstraintsV2(),
        "count_policy": CountPolicy(mode="best_effort", target=3, minimum=1),
        "output_requirements": OutputRequirementsV2(
            output_types=("digest",),
            language="zh-CN",
        ),
        "quality_policy_id": "quality-v2",
        "policy_version": "2026-09-17",
    }
    values.update(changes)
    return ResearchBriefV2.model_validate(values)


def _document(document_id: str, **changes: object) -> SourceDocumentV2:
    values: dict[str, object] = {
        "document_id": document_id,
        "candidate_id": f"candidate-{document_id}",
        "source_id": "source-1",
        "source_item_id": document_id,
        "source_item_version": "v1",
        "original_url": f"https://news.example/read?id={document_id}",
        "canonical_url": f"https://news.example/read?id={document_id}",
        "publisher_id": "news.example",
        "ownership_group": None,
        "title": "同义表达的技术突破",
        "text": "该系统在复杂任务上取得新的结果。",
        "content_hash": (document_id[-1] if document_id[-1].isalnum() else "a") * 64,
        "artifact_ref": f"inline:sha256:{document_id}",
        "discovered_via": "api",
        "content_scope": "full",
        "published_at": datetime(2026, 9, 15, 8, tzinfo=UTC),
        "published_interval_end": None,
        "published_timezone_known": True,
        "time_precision": "exact",
        "updated_at": None,
        "event_at": None,
        "first_published_at": datetime(2026, 9, 15, 8, tzinfo=UTC),
        "first_seen_at": None,
        "fetched_at": None,
        "extractor_version": "extractor/2",
        "resource_status": "accepted",
        "language": None,
        "event_region": None,
        "source_role": "reporting",
    }
    values.update(changes)
    return SourceDocumentV2.model_validate(values)


def _decision(
    brief: ResearchBriefV2,
    document: SourceDocumentV2,
    outcome: str = "relevant",
) -> SemanticRelevanceDecisionV2:
    return SemanticRelevanceDecisionV2(
        document_id=document.document_id,
        document_content_hash=document.content_hash,
        brief_digest=brief.canonical_digest(),
        outcome=outcome,
        requirement_ids=(),
        source_excerpt=document.text[:40],
        prompt_version=RELEVANCE_PROMPT_VERSION,
    )


def test_semantically_relevant_without_topic_keyword_is_accepted() -> None:
    brief = _brief()
    document = _document("doc-a")

    result = filter_documents(brief, (document,), (_decision(brief, document),))

    assert result.accepted_document_ids == ("doc-a",)
    assert result.rejected == ()
    assert result.uncertain == ()


def test_old_repost_uses_first_confirmed_publication_time() -> None:
    brief = _brief()
    document = _document(
        "doc-b",
        published_at=datetime(2026, 9, 15, 8, tzinfo=UTC),
        first_published_at=datetime(2026, 8, 1, 8, tzinfo=UTC),
    )

    result = filter_documents(brief, (document,), (_decision(brief, document),))

    assert result.accepted_document_ids == ()
    assert result.rejected[0].reason_code == "TIME_OUTSIDE_WINDOW"


def test_unknown_date_is_uncertain_not_accepted_or_rejected() -> None:
    brief = _brief()
    document = _document(
        "doc-c",
        published_at=None,
        first_published_at=None,
        published_timezone_known=False,
        time_precision="unknown",
    )

    result = filter_documents(brief, (document,), (_decision(brief, document),))

    assert result.accepted_document_ids == ()
    assert result.rejected == ()
    assert result.uncertain[0].reason_code == "TIME_UNKNOWN"


def test_date_interval_partial_overlap_is_uncertain() -> None:
    brief = _brief()
    document = _document(
        "doc-d",
        published_at=datetime(2026, 9, 14, 12, tzinfo=UTC),
        published_interval_end=datetime(2026, 9, 15, 12, tzinfo=UTC),
        first_published_at=None,
        time_precision="day",
    )

    result = filter_documents(brief, (document,), (_decision(brief, document),))

    assert result.uncertain[0].reason_code == "TIME_PARTIAL_OVERLAP"


def test_stale_or_uncertain_semantic_decision_does_not_default_true() -> None:
    brief = _brief()
    document = _document("doc-e")
    stale = _decision(brief, document).model_copy(
        update={"document_content_hash": "f" * 64}
    )

    result = filter_documents(brief, (document,), (stale,))

    assert result.uncertain[0].reason_code == "SEMANTIC_DECISION_STALE"

    uncertain = filter_documents(
        brief,
        (document,),
        (_decision(brief, document, "uncertain"),),
    )
    assert uncertain.uncertain[0].reason_code == "SEMANTIC_UNCERTAIN"

    stale_prompt = _decision(brief, document).model_copy(
        update={"prompt_version": "research.v2.relevance@0.9.0"}
    )
    stale_result = filter_documents(brief, (document,), (stale_prompt,))
    assert stale_result.uncertain[0].reason_code == "SEMANTIC_DECISION_STALE"


def test_decision_for_unknown_document_is_rejected() -> None:
    brief = _brief()
    document = _document("doc-known")
    foreign = _decision(brief, _document("doc-foreign"))

    with pytest.raises(ValueError, match="SEMANTIC_DECISION_DOCUMENT_UNKNOWN"):
        filter_documents(brief, (document,), (foreign,))


def test_source_constraints_and_count_conservation() -> None:
    brief = _brief(
        source_constraints=SourceConstraintsV2(
            allowed_source_ids=("source-1",),
            excluded_source_ids=("source-2",),
        )
    )
    accepted = _document("doc-f")
    rejected = _document("doc-g", source_id="source-2")
    unknown = _document("doc-h", published_at=None, first_published_at=None, time_precision="unknown", published_timezone_known=False)

    result = filter_documents(
        brief,
        (accepted, rejected, unknown),
        (
            _decision(brief, accepted),
            _decision(brief, rejected),
            _decision(brief, unknown),
        ),
    )

    assert result.input_count == 3
    assert result.accepted_count + result.rejected_count + result.uncertain_count == 3
    assert {item.document_id for item in result.rejected} == {"doc-g"}
    assert {item.document_id for item in result.uncertain} == {"doc-h"}
