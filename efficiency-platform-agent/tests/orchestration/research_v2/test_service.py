"""X03 ResearchService 通过唯一图执行并按 ID 物化结果。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from efficiency_platform_agent.contracts.research_v2 import (
    BudgetSnapshotV2,
    ResearchOutcomeV2,
    ResearchPolicySnapshotV2,
    ResearchRuntimeContextV2,
    ResearchUsageV2,
)
from efficiency_platform_agent.orchestration.research_v2.graph import (
    ResearchStageUpdateV2,
)
from efficiency_platform_agent.orchestration.research_v2.service import (
    LangGraphResearchServiceV2,
)
from tests.unit.capabilities.research_v2._delivery_support import delivery_facts


class _Runner:
    async def run_stage(self, stage, state):
        del state
        updates = {
            "plan": ResearchStageUpdateV2(planned_action_ids=("action-1",)),
            "discover": ResearchStageUpdateV2(candidate_ids=("candidate-1",)),
            "acquire": ResearchStageUpdateV2(
                acquired_document_ids=("doc-1",), evidence_ids=("evidence-1",)
            ),
            "normalize": ResearchStageUpdateV2(normalized_document_ids=("doc-1",)),
            "filter": ResearchStageUpdateV2(filtered_document_ids=("doc-1",)),
            "deduplicate": ResearchStageUpdateV2(deduplicated_document_ids=("doc-1",)),
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


class _Materializer:
    async def materialize(self, brief, state):
        del brief
        return ResearchOutcomeV2(
            outcome=state["domain_status"],
            usable_event_ids=tuple(state["qualified_event_ids"]),
            evidence_ids=tuple(state["evidence_ids"]),
            stop_reason=state["stop_reason"],
            usage=ResearchUsageV2(
                source_requests=1, model_calls=0, downloaded_bytes=10
            ),
        )


@pytest.mark.asyncio
async def test_service_runs_unique_graph_and_materializes_matching_ids() -> None:
    brief, *_ = delivery_facts()
    brief_policy = ResearchPolicySnapshotV2(
        quality_policy_id=brief.quality_policy_id, policy_version=brief.policy_version
    )
    service = LangGraphResearchServiceV2(
        policy=brief_policy,
        budget=BudgetSnapshotV2(
            lease_id=brief.trusted_context.budget_lease_id,
            version=0,
            remaining_calls=10,
            remaining_bytes=1000,
        ),
        stage_runner=_Runner(),
        materializer=_Materializer(),
        now=lambda: datetime(2026, 9, 16, tzinfo=UTC),
    )
    outcome = await service.research(
        brief,
        ResearchRuntimeContextV2(
            request_id="request-1",
            started_at=datetime(2026, 9, 16, tzinfo=UTC),
            deadline=datetime(2026, 9, 16, tzinfo=UTC) + timedelta(minutes=3),
        ),
    )
    assert outcome.outcome == "COMPLETE"
    assert outcome.usable_event_ids == ("event-1",)
    assert outcome.evidence_ids == ("evidence-1",)
