"""R09 补采动作的范围、指纹、来源与预算门禁。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from efficiency_platform_agent.contracts.intent_v2 import (
    OutputRequirementsV2,
    SourceConstraintsV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    BudgetSnapshotV2,
    CollectionActionV2,
    CollectionHistoryV2,
    CollectionPlanV2,
    CountPolicy,
    QualityGapV2,
    QualityReportV2,
    ResearchBriefV2,
    TrustedResearchContextV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from efficiency_platform_agent.orchestration.research_v2.planner import (
    ActionValidator,
    CollectionPlanner,
    PlanningSourceRegistryV2,
    PlanningSourceV2,
    action_fingerprint,
)


def _brief() -> ResearchBriefV2:
    return ResearchBriefV2(
        trusted_context=TrustedResearchContextV2(
            tenant_id="t", run_id="r", task_id="x", budget_lease_id="lease"
        ),
        intent_revision=2,
        topic="AI",
        time_window=ResolvedTimeWindow(
            start=datetime(2026, 9, 15, tzinfo=UTC),
            end=datetime(2026, 9, 16, tzinfo=UTC),
            timezone="UTC",
            precision="day",
            original_text="yesterday",
            anchor=datetime(2026, 9, 16, tzinfo=UTC),
        ),
        source_constraints=SourceConstraintsV2(),
        count_policy=CountPolicy(mode="exact", target=5, minimum=1),
        output_requirements=OutputRequirementsV2(
            output_types=("digest",), language="zh-CN"
        ),
        quality_policy_id="quality-v2",
        policy_version="v2",
    )


def _gap() -> QualityGapV2:
    return QualityGapV2(
        gap_id="gap-count",
        requirement_id="count_policy",
        code="COUNT_EXACT_UNMET",
        detail="need more",
        recoverable=True,
    )


def _quality(*, gaps=None) -> QualityReportV2:
    return QualityReportV2(
        report_id="quality-1",
        brief_digest=_brief().canonical_digest(),
        policy_version="v2",
        hard_gates_passed=False,
        gaps=(_gap(),) if gaps is None else gaps,
        coverage_ratio=1.0,
    )


def _registry() -> PlanningSourceRegistryV2:
    return PlanningSourceRegistryV2(
        sources=(
            PlanningSourceV2(
                source_id="source-free",
                roles=("reporting",),
                admitted=True,
                verified_free=True,
            ),
        )
    )


def _action(brief=None, gap=None, source_id="source-free", window=None):
    brief = brief or _brief()
    gap = gap or _gap()
    query = "  AI   updates "
    return CollectionActionV2(
        action_id=action_fingerprint(
            brief.intent_revision, gap, source_id, query, None
        ),
        gap_id=gap.gap_id,
        gap_code=gap.code,
        action_kind="search_alternative",
        source_id=source_id,
        requirement_ids=(gap.requirement_id,),
        query=query,
        time_window=window or brief.time_window,
        revision=0,
    )


def _budget(calls=3):
    return BudgetSnapshotV2(
        lease_id="lease", version=0, remaining_calls=calls, remaining_bytes=1000
    )


def test_completed_action_is_rejected_without_reexecution() -> None:
    action = _action()
    result = ActionValidator().validate(
        CollectionPlanV2(actions=(action,)),
        _brief(),
        _quality(),
        _registry(),
        CollectionHistoryV2(
            completed_action_ids=(action.action_id,), rounds=1, no_gain_rounds=0
        ),
        _budget(),
    )
    assert result.actions == ()
    assert result.rejected[0].reason_code == "ACTION_ALREADY_COMPLETED"


@pytest.mark.parametrize("failure", ["time", "source", "fingerprint", "no_gap"])
def test_scope_source_fingerprint_and_gap_fail_closed(failure: str) -> None:
    brief = _brief()
    action = _action(brief=brief)
    quality = _quality()
    if failure == "time":
        action = _action(
            brief=brief,
            window=brief.time_window.model_copy(
                update={"start": brief.time_window.start - timedelta(days=1)}
            ),
        )
        expected = "PLAN_TIME_SCOPE_EXPANDED"
    elif failure == "source":
        action = _action(brief=brief, source_id="source-unknown")
        expected = "PLAN_SOURCE_UNREGISTERED"
    elif failure == "fingerprint":
        action = action.model_copy(update={"action_id": "action-tampered"})
        expected = "PLAN_ACTION_FINGERPRINT_INVALID"
    else:
        quality = _quality(gaps=())
        expected = "PLAN_WITHOUT_GAP"
    with pytest.raises(ValueError, match=expected):
        ActionValidator().validate(
            CollectionPlanV2(actions=(action,)),
            brief,
            quality,
            _registry(),
            CollectionHistoryV2(rounds=0, no_gain_rounds=0),
            _budget(),
        )


def test_model_cannot_declare_research_complete() -> None:
    with pytest.raises(ValueError, match="MODEL_COMPLETION_FORBIDDEN"):
        ActionValidator().validate(
            CollectionPlanV2(actions=(), stop_reason="RESEARCH_COMPLETE"),
            _brief(),
            _quality(),
            _registry(),
            CollectionHistoryV2(rounds=0, no_gain_rounds=0),
            _budget(),
        )


def test_fact_blocker_is_ordered_before_count_gap() -> None:
    brief = _brief()
    count_gap = _gap()
    fact_gap = QualityGapV2(
        gap_id="gap-time",
        requirement_id="time_window",
        code="TIME_UNKNOWN",
        detail="time missing",
        recoverable=True,
    )
    quality = _quality(gaps=(count_gap, fact_gap))
    count_action = _action(brief=brief, gap=count_gap)
    fact_action = CollectionActionV2(
        action_id=action_fingerprint(
            brief.intent_revision,
            fact_gap,
            "source-free",
            "AI event time",
            None,
        ),
        gap_id=fact_gap.gap_id,
        gap_code=fact_gap.code,
        action_kind="verify_time",
        source_id="source-free",
        requirement_ids=(fact_gap.requirement_id,),
        query="AI event time",
        time_window=brief.time_window,
        revision=0,
    )

    result = ActionValidator().validate(
        CollectionPlanV2(actions=(count_action, fact_action)),
        brief,
        quality,
        _registry(),
        CollectionHistoryV2(rounds=0, no_gain_rounds=0),
        _budget(),
    )

    assert [item.gap_code for item in result.actions] == [
        "TIME_UNKNOWN",
        "COUNT_EXACT_UNMET",
    ]


class _NeverCalledPort:
    called = False

    async def propose(self, brief, quality, history, budget):
        self.called = True
        raise AssertionError("must not call model")


@pytest.mark.asyncio
async def test_no_gap_is_deterministic_quality_met_without_model() -> None:
    port = _NeverCalledPort()
    plan = await CollectionPlanner(port).plan_gaps(
        _brief(),
        _quality(gaps=()),
        CollectionHistoryV2(rounds=0, no_gain_rounds=0),
        _budget(),
    )
    assert plan.stop_reason == "QUALITY_MET"
    assert port.called is False
