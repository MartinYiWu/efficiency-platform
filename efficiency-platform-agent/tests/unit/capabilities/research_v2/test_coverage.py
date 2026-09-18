"""R08 成功空、失败空和历史未知状态测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from efficiency_platform_agent.capabilities.research.v2.claims import ConflictResolver
from efficiency_platform_agent.capabilities.research.v2.filtering import FilterResultV2
from efficiency_platform_agent.capabilities.research.v2.quality import (
    CollectionCoverageV2,
    evaluate_quality,
)
from efficiency_platform_agent.contracts.intent_v2 import (
    OutputRequirementsV2,
    SourceConstraintsV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    CountPolicy,
    ResearchBriefV2,
    ResearchPolicySnapshotV2,
    TrustedResearchContextV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow


def _brief():
    return ResearchBriefV2(
        trusted_context=TrustedResearchContextV2(
            tenant_id="tenant-1", run_id="run-1", task_id="task-1", budget_lease_id="lease-1"
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
        count_policy=CountPolicy(mode="best_effort", target=5, minimum=1),
        output_requirements=OutputRequirementsV2(output_types=("digest",), language="zh-CN"),
        quality_policy_id="research-quality-v2",
        policy_version="2026-09-17",
    )


def _policy():
    return ResearchPolicySnapshotV2(
        quality_policy_id="research-quality-v2",
        policy_version="research-quality/2.0.0-offline",
    )


def _empty(collection: CollectionCoverageV2):
    return evaluate_quality(
        _brief(),
        _policy(),
        (),
        (),
        (),
        (),
        FilterResultV2(
            input_count=0, accepted_count=0, rejected_count=0, uncertain_count=0
        ),
        ConflictResolver().classify(()),
        (),
        collection,
    )


def test_complete_plan_with_complete_history_can_be_no_matches() -> None:
    result = _empty(
        CollectionCoverageV2(
            plan_complete=True,
            attempt_count=3,
            historical_coverage="complete",
        )
    )

    assert result.outcome == "NO_MATCHES"


def test_all_failed_or_history_unknown_is_failed_not_no_matches() -> None:
    failed = _empty(
        CollectionCoverageV2(
            plan_complete=False,
            attempt_count=3,
            critical_failure=True,
            historical_coverage="unknown",
        )
    )
    unknown_history = _empty(
        CollectionCoverageV2(
            plan_complete=True,
            attempt_count=1,
            historical_coverage="unknown",
        )
    )

    assert failed.outcome == "FAILED"
    assert unknown_history.outcome == "FAILED"
    assert all(
        item.code == "COLLECTION_INCOMPLETE"
        for result in (failed, unknown_history)
        for item in result.report.gaps
        if item.requirement_id == "collection"
    )


def test_truncated_plan_cannot_claim_no_matches() -> None:
    result = _empty(
        CollectionCoverageV2(
            plan_complete=True,
            attempt_count=2,
            truncated=True,
            historical_coverage="complete",
        )
    )

    assert result.outcome == "FAILED"
