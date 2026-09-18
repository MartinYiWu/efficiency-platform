"""ResearchServiceV2 对唯一 LangGraph 子图的正式适配层。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from efficiency_platform_agent.contracts.research_v2 import (
    BudgetSnapshotV2,
    ResearchBriefV2,
    ResearchOutcomeV2,
    ResearchPolicySnapshotV2,
    ResearchRuntimeContextV2,
)

from .graph import ResearchGraphDependencies, ResearchStageRunner, build_research_graph
from .state import ResearchGraphState, initial_research_state


@runtime_checkable
class ResearchOutcomeMaterializer(Protocol):
    async def materialize(
        self,
        brief: ResearchBriefV2,
        state: ResearchGraphState,
    ) -> ResearchOutcomeV2: ...


class LangGraphResearchServiceV2:
    """不创建第二 Runtime；结果正文由 Materializer 按状态 ID 读取。"""

    def __init__(
        self,
        *,
        policy: ResearchPolicySnapshotV2,
        budget: BudgetSnapshotV2,
        stage_runner: ResearchStageRunner,
        materializer: ResearchOutcomeMaterializer,
        checkpointer=None,
        now=lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(stage_runner, ResearchStageRunner):
            raise TypeError("stage_runner 必须实现 ResearchStageRunner")
        if not isinstance(materializer, ResearchOutcomeMaterializer):
            raise TypeError("materializer 必须实现 ResearchOutcomeMaterializer")
        self.policy = policy
        self.budget = budget
        self.materializer = materializer
        self.now = now
        self.graph = build_research_graph(
            ResearchGraphDependencies(stage_runner),
            checkpointer=checkpointer,
        )

    async def research(
        self,
        brief: ResearchBriefV2,
        runtime_context: ResearchRuntimeContextV2,
    ) -> ResearchOutcomeV2:
        if brief.trusted_context.budget_lease_id != self.budget.lease_id:
            raise ValueError("RESEARCH_SERVICE_BUDGET_MISMATCH")
        if brief.quality_policy_id != self.policy.quality_policy_id:
            raise ValueError("RESEARCH_SERVICE_POLICY_MISMATCH")
        if self.now() >= runtime_context.deadline:
            raise TimeoutError("RESEARCH_SERVICE_HARD_DEADLINE")
        initial = initial_research_state(
            brief,
            self.policy,
            self.budget,
            max_refill_rounds=min(2, self.policy.max_collection_rounds - 1),
        )
        thread_id = (
            f"{brief.trusted_context.tenant_id}:"
            f"{brief.trusted_context.run_id}:{runtime_context.request_id}"
        )
        result = await self.graph.ainvoke(
            initial,
            config={"configurable": {"thread_id": thread_id}},
        )
        state = ResearchGraphState(**result)
        outcome = await self.materializer.materialize(brief, state)
        if tuple(state.get("qualified_event_ids", ())) != outcome.usable_event_ids:
            raise ValueError("RESEARCH_OUTCOME_EVENT_MISMATCH")
        if not set(outcome.evidence_ids).issubset(state.get("evidence_ids", ())):
            raise ValueError("RESEARCH_OUTCOME_EVIDENCE_MISMATCH")
        if state.get("domain_status") != outcome.outcome:
            raise ValueError("RESEARCH_OUTCOME_STATUS_MISMATCH")
        if state.get("stop_reason") != outcome.stop_reason:
            raise ValueError("RESEARCH_OUTCOME_STOP_REASON_MISMATCH")
        return outcome


__all__ = ["LangGraphResearchServiceV2", "ResearchOutcomeMaterializer"]
