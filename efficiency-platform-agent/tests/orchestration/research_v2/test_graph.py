"""R09 LangGraph 节点序列和只存 ID 状态测试。"""

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
)
from efficiency_platform_agent.orchestration.research_v2.state import (
    ResearchGraphState,
    initial_research_state,
)


def _state() -> ResearchGraphState:
    brief = ResearchBriefV2(
        trusted_context=TrustedResearchContextV2(
            tenant_id="t",
            run_id="r",
            task_id="x",
            budget_lease_id="lease",
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
            output_types=("digest",),
            language="zh-CN",
        ),
        quality_policy_id="quality-v2",
        policy_version="v2",
    )
    return initial_research_state(
        brief,
        ResearchPolicySnapshotV2(
            quality_policy_id="quality-v2",
            policy_version="v2",
        ),
        BudgetSnapshotV2(
            lease_id="lease",
            version=0,
            remaining_calls=10,
            remaining_bytes=1000,
        ),
    )


class _CompleteRunner:
    def __init__(self) -> None:
        self.calls = []

    async def run_stage(self, stage, state):
        self.calls.append(stage)
        updates = {
            "plan": ResearchStageUpdateV2(planned_action_ids=("action-1",)),
            "discover": ResearchStageUpdateV2(candidate_ids=("candidate-1",)),
            "acquire": ResearchStageUpdateV2(
                acquired_document_ids=("document-1",), evidence_ids=("evidence-1",)
            ),
            "normalize": ResearchStageUpdateV2(normalized_document_ids=("document-1",)),
            "filter": ResearchStageUpdateV2(filtered_document_ids=("document-1",)),
            "deduplicate": ResearchStageUpdateV2(
                deduplicated_document_ids=("document-1",)
            ),
            "cluster": ResearchStageUpdateV2(event_ids=("event-1",)),
            "claims": ResearchStageUpdateV2(claim_ids=("claim-1",)),
            "quality": ResearchStageUpdateV2(
                quality_report_id="quality-1",
                qualified_event_ids=("event-1",),
                hard_gap_ids=(),
            ),
            "verify": ResearchStageUpdateV2(output_verified=True),
            "render": ResearchStageUpdateV2(output_artifact_id="artifact-1"),
        }
        return updates.get(stage, ResearchStageUpdateV2())


@pytest.mark.asyncio
async def test_complete_path_requires_compose_verify_and_render() -> None:
    runner = _CompleteRunner()
    graph = build_research_graph(ResearchGraphDependencies(runner))
    result = await graph.ainvoke(
        _state(), config={"configurable": {"thread_id": "complete"}}
    )

    assert result["domain_status"] == "COMPLETE"
    assert result["stop_reason"] == "QUALITY_MET"
    assert result["output_artifact_id"] == "artifact-1"
    assert runner.calls == [
        "validate",
        "plan",
        "discover",
        "acquire",
        "normalize",
        "filter",
        "deduplicate",
        "cluster",
        "claims",
        "quality",
        "compose",
        "verify",
        "render",
        "finalize",
    ]


def test_graph_state_contract_has_no_fulltext_or_prompt_fields() -> None:
    forbidden = {
        "documents",
        "document_text",
        "content",
        "html",
        "prompt",
        "model_output",
    }
    assert forbidden.isdisjoint(ResearchGraphState.__annotations__)
