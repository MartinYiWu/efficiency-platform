"""缺口到受控补采动作的提案与确定性验证。"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.contracts.research_v2 import (
    BudgetSnapshotV2,
    CollectionActionV2,
    CollectionHistoryV2,
    CollectionPlanV2,
    QualityGapV2,
    QualityReportV2,
    ResearchBriefV2,
)

_GAP_ACTIONS: dict[str, frozenset[str]] = {
    "INSUFFICIENT_EVENTS": frozenset({"search_alternative"}),
    "COUNT_EXACT_UNMET": frozenset({"search_alternative"}),
    "COUNT_MINIMUM_UNMET": frozenset({"search_alternative"}),
    "MISSING_REQUIRED_FACET": frozenset({"search_required_facet"}),
    "REQUIRED_FACET_UNCOVERED": frozenset({"search_required_facet"}),
    "PRIMARY_SOURCE_MISSING": frozenset({"locate_primary"}),
    "CONTENT_UNAVAILABLE": frozenset({"fetch_content"}),
    "TIME_UNKNOWN": frozenset({"verify_time"}),
    "CONFLICT_UNRESOLVED": frozenset({"resolve_conflict"}),
    "HEAT_UNSUPPORTED": frozenset({"observe_heat"}),
    "SOURCE_TEMPORARY_FAILURE": frozenset({"retry_or_alternate"}),
    "FREE_QUOTA_EXHAUSTED": frozenset({"switch_free_source"}),
    "SOURCE_COST_UNVERIFIED": frozenset({"switch_free_source"}),
    "HISTORY_COVERAGE_UNKNOWN": frozenset({"verify_history"}),
    "OUTPUT_FORMAT_INVALID": frozenset({"rerender_only"}),
}

_GAP_PRIORITY: dict[str, int] = {
    "PRIMARY_SOURCE_MISSING": 0,
    "CONTENT_UNAVAILABLE": 0,
    "TIME_UNKNOWN": 0,
    "CONFLICT_UNRESOLVED": 0,
    "SOURCE_TEMPORARY_FAILURE": 0,
    "FREE_QUOTA_EXHAUSTED": 0,
    "SOURCE_COST_UNVERIFIED": 0,
    "HISTORY_COVERAGE_UNKNOWN": 0,
    "MISSING_REQUIRED_FACET": 1,
    "REQUIRED_FACET_UNCOVERED": 1,
    "INSUFFICIENT_EVENTS": 2,
    "COUNT_EXACT_UNMET": 2,
    "COUNT_MINIMUM_UNMET": 2,
    "HEAT_UNSUPPORTED": 3,
    "OUTPUT_FORMAT_INVALID": 4,
}


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PlanningSourceV2(_FrozenContract):
    source_id: str = Field(min_length=1, max_length=128)
    roles: tuple[str, ...] = Field(min_length=1, max_length=8)
    admitted: bool
    verified_free: bool
    supports_history: bool = False


class PlanningSourceRegistryV2(_FrozenContract):
    sources: tuple[PlanningSourceV2, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def validate_unique(self) -> PlanningSourceRegistryV2:
        if len({item.source_id for item in self.sources}) != len(self.sources):
            raise ValueError("PLANNING_SOURCE_DUPLICATED")
        return self

    def get(self, source_id: str) -> PlanningSourceV2 | None:
        return next(
            (item for item in self.sources if item.source_id == source_id), None
        )


class RejectedActionV2(_FrozenContract):
    action_id: str = Field(min_length=1, max_length=128)
    reason_code: str = Field(min_length=1, max_length=128)


class ValidatedPlanV2(_FrozenContract):
    actions: tuple[CollectionActionV2, ...] = Field(default=(), max_length=128)
    rejected: tuple[RejectedActionV2, ...] = Field(default=(), max_length=128)
    stop_reason: str | None = Field(default=None, min_length=1, max_length=128)


@runtime_checkable
class CollectionPlanProposalPort(Protocol):
    async def propose(
        self,
        brief: ResearchBriefV2,
        quality: QualityReportV2,
        history: CollectionHistoryV2,
        budget: BudgetSnapshotV2,
    ) -> CollectionPlanV2: ...


class CollectionPlanner:
    def __init__(self, proposal_port: CollectionPlanProposalPort) -> None:
        if not isinstance(proposal_port, CollectionPlanProposalPort):
            raise TypeError("proposal_port 必须实现 CollectionPlanProposalPort")
        self._proposal_port = proposal_port

    async def plan_gaps(
        self,
        brief: ResearchBriefV2,
        quality: QualityReportV2,
        history: CollectionHistoryV2,
        budget: BudgetSnapshotV2,
    ) -> CollectionPlanV2:
        if not quality.gaps:
            return CollectionPlanV2(actions=(), stop_reason="QUALITY_MET")
        return await self._proposal_port.propose(brief, quality, history, budget)


class ActionValidator:
    def validate(
        self,
        plan: CollectionPlanV2,
        brief: ResearchBriefV2,
        quality: QualityReportV2,
        registry: PlanningSourceRegistryV2,
        history: CollectionHistoryV2,
        budget: BudgetSnapshotV2,
    ) -> ValidatedPlanV2:
        gaps = {item.gap_id: item for item in quality.gaps}
        if not gaps:
            if plan.actions:
                raise ValueError("PLAN_WITHOUT_GAP")
            return ValidatedPlanV2(actions=(), stop_reason="QUALITY_MET")
        if not plan.actions:
            if plan.stop_reason in {"RESEARCH_COMPLETE", "QUALITY_MET"}:
                raise ValueError("MODEL_COMPLETION_FORBIDDEN")
            return ValidatedPlanV2(actions=(), stop_reason=plan.stop_reason)
        action_ids = [item.action_id for item in plan.actions]
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("PLAN_ACTION_DUPLICATED")
        accepted: list[CollectionActionV2] = []
        rejected: list[RejectedActionV2] = []
        completed = set(history.completed_action_ids)
        ordered_actions = sorted(
            plan.actions,
            key=lambda item: (
                _GAP_PRIORITY.get(item.gap_code, 99),
                item.source_id,
                item.action_id,
            ),
        )
        for action in ordered_actions:
            gap = gaps.get(action.gap_id)
            if gap is None or action.gap_code != gap.code:
                raise ValueError("PLAN_GAP_UNKNOWN")
            allowed = _GAP_ACTIONS.get(gap.code)
            if allowed is None or action.action_kind not in allowed:
                raise ValueError("PLAN_ACTION_KIND_FORBIDDEN")
            if action.time_window != brief.time_window:
                raise ValueError("PLAN_TIME_SCOPE_EXPANDED")
            if action.requirement_ids != (gap.requirement_id,):
                raise ValueError("PLAN_REQUIREMENT_SCOPE_INVALID")
            expected = action_fingerprint(
                brief.intent_revision,
                gap,
                action.source_id,
                action.query,
                action.cursor,
            )
            if action.action_id != expected:
                raise ValueError("PLAN_ACTION_FINGERPRINT_INVALID")
            if action.action_id in completed:
                rejected.append(
                    RejectedActionV2(
                        action_id=action.action_id,
                        reason_code="ACTION_ALREADY_COMPLETED",
                    )
                )
                continue
            if action.action_kind == "rerender_only":
                if action.source_id != "internal.renderer":
                    raise ValueError("PLAN_INTERNAL_ACTION_INVALID")
            else:
                source = registry.get(action.source_id)
                if source is None:
                    raise ValueError("PLAN_SOURCE_UNREGISTERED")
                if not source.admitted or not source.verified_free:
                    raise ValueError("PLAN_SOURCE_NOT_ALLOWED")
                if (
                    action.action_kind == "locate_primary"
                    and "primary" not in source.roles
                ):
                    raise ValueError("PLAN_PRIMARY_SOURCE_REQUIRED")
                if (
                    action.action_kind == "verify_history"
                    and not source.supports_history
                ):
                    raise ValueError("PLAN_HISTORY_SOURCE_REQUIRED")
            accepted.append(action)
        if len(accepted) > budget.remaining_calls:
            raise ValueError("PLAN_BUDGET_EXCEEDED")
        stop_reason = plan.stop_reason if not accepted else None
        return ValidatedPlanV2(
            actions=tuple(accepted), rejected=tuple(rejected), stop_reason=stop_reason
        )


def action_fingerprint(
    intent_revision: int,
    gap: QualityGapV2,
    source_id: str,
    query: str,
    cursor: str | None,
) -> str:
    normalized_query = re.sub(r"\s+", " ", query).strip().casefold()
    value = "\x00".join(
        (
            str(intent_revision),
            gap.gap_id,
            gap.code,
            source_id,
            normalized_query,
            cursor or "",
        )
    )
    return "action-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


__all__ = [
    "ActionValidator",
    "CollectionPlanProposalPort",
    "CollectionPlanner",
    "PlanningSourceRegistryV2",
    "PlanningSourceV2",
    "RejectedActionV2",
    "ValidatedPlanV2",
    "action_fingerprint",
]
