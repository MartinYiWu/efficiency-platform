"""R09 无增益、取消、硬截止和状态裁决测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from efficiency_platform_agent.contracts.intent_v2 import (
    OutputRequirementsV2,
    SourceConstraintsV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    BudgetSnapshotV2,
    CountPolicy,
    ResearchBriefV2,
    ResearchPolicySnapshotV2,
    TrustedResearchContextV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from efficiency_platform_agent.orchestration.research_v2.graph import (
    ResearchGraphDependencies,
    ResearchStageUpdateV2,
    build_research_graph,
    stopped_research_status,
)
from efficiency_platform_agent.orchestration.research_v2.state import (
    initial_research_state,
)


def _state():
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
    return initial_research_state(
        brief,
        ResearchPolicySnapshotV2(quality_policy_id="quality-v2", policy_version="v2"),
        BudgetSnapshotV2(
            lease_id="lease", version=0, remaining_calls=10, remaining_bytes=1000
        ),
    )


class _NoGainRunner:
    def __init__(self) -> None:
        self.quality_calls = 0
        self.calls = []

    async def run_stage(self, stage, state):
        self.calls.append(stage)
        if stage == "plan":
            return ResearchStageUpdateV2(
                planned_action_ids=(
                    f"action-{len([x for x in self.calls if x == 'plan'])}",
                ),
                plan_exhausted=False,
            )
        if stage == "acquire":
            return ResearchStageUpdateV2(
                acquired_document_ids=("document-1",), evidence_ids=("evidence-1",)
            )
        if stage == "claims":
            return ResearchStageUpdateV2(claim_ids=("claim-1",))
        if stage == "quality":
            self.quality_calls += 1
            return ResearchStageUpdateV2(
                quality_report_id=f"quality-{self.quality_calls}",
                qualified_event_ids=("event-1",),
                claim_ids=("claim-1",),
                evidence_ids=("evidence-1",),
                hard_gap_ids=("gap-1",),
            )
        return ResearchStageUpdateV2()


@pytest.mark.asyncio
async def test_two_no_gain_refills_stop_and_keep_evidence_ids() -> None:
    graph = build_research_graph(ResearchGraphDependencies(_NoGainRunner()))
    result = await graph.ainvoke(
        _state(), config={"configurable": {"thread_id": "no-gain"}}
    )

    assert result["refill_rounds"] == 2
    assert result["no_gain_rounds"] == 2
    assert result["stop_reason"] == "NO_GAIN"
    assert result["domain_status"] == "PARTIAL"
    assert result["qualified_event_ids"] == ["event-1"]
    assert result["evidence_ids"] == ["evidence-1"]


class _StopRunner:
    def __init__(self, field):
        self.field = field
        self.calls = []

    async def run_stage(self, stage, state):
        self.calls.append(stage)
        if stage == "validate":
            return ResearchStageUpdateV2.model_validate({self.field: True})
        return ResearchStageUpdateV2()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "reason"),
    [("cancelled", "USER_CANCELLED"), ("hard_deadline_reached", "HARD_DEADLINE")],
)
async def test_cancel_and_hard_deadline_stop_before_collection(field, reason) -> None:
    runner = _StopRunner(field)
    graph = build_research_graph(ResearchGraphDependencies(runner))
    result = await graph.ainvoke(
        _state(), config={"configurable": {"thread_id": field}}
    )

    assert result["stop_reason"] == reason
    assert result["domain_status"] == "NOT_EVALUATED"
    assert runner.calls == ["validate", "finalize"]


def test_stopped_status_never_accepts_quality_without_verified_output() -> None:
    assert stopped_research_status(3, 0, False, False) == "PARTIAL"
    assert stopped_research_status(3, 0, False, True) == "COMPLETE"
    assert stopped_research_status(0, 0, True, False) == "NO_MATCHES"
    assert stopped_research_status(0, 1, False, False) == "FAILED"
