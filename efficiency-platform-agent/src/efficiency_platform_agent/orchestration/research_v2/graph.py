"""唯一 LangGraph Runtime 内的有界 Research V2 子图。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, cast, runtime_checkable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from .state import ResearchGraphState

ResearchStage = Literal[
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


class ResearchStageUpdateV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    planned_action_ids: tuple[str, ...] | None = Field(default=None, max_length=128)
    candidate_ids: tuple[str, ...] | None = Field(default=None, max_length=10_000)
    acquired_document_ids: tuple[str, ...] | None = Field(
        default=None, max_length=2_000
    )
    normalized_document_ids: tuple[str, ...] | None = Field(
        default=None, max_length=2_000
    )
    filtered_document_ids: tuple[str, ...] | None = Field(
        default=None, max_length=2_000
    )
    deduplicated_document_ids: tuple[str, ...] | None = Field(
        default=None, max_length=2_000
    )
    event_ids: tuple[str, ...] | None = Field(default=None, max_length=1_000)
    qualified_event_ids: tuple[str, ...] | None = Field(default=None, max_length=1_000)
    claim_ids: tuple[str, ...] | None = Field(default=None, max_length=10_000)
    evidence_ids: tuple[str, ...] | None = Field(default=None, max_length=20_000)
    quality_report_id: str | None = Field(default=None, max_length=128)
    hard_gap_ids: tuple[str, ...] | None = Field(default=None, max_length=256)
    output_artifact_id: str | None = Field(default=None, max_length=128)
    output_verified: bool | None = None
    output_degraded: bool | None = None
    output_recollect_requested: bool | None = None
    complete_empty_plan: bool | None = None
    plan_exhausted: bool | None = None
    budget_exhausted: bool | None = None
    soft_deadline_reached: bool | None = None
    hard_deadline_reached: bool | None = None
    cancelled: bool | None = None
    fatal_error: bool | None = None
    budget_version: int | None = Field(default=None, ge=0)


@runtime_checkable
class ResearchStageRunner(Protocol):
    async def run_stage(
        self,
        stage: ResearchStage,
        state: ResearchGraphState,
    ) -> ResearchStageUpdateV2: ...


@dataclass(frozen=True, slots=True)
class ResearchGraphDependencies:
    stage_runner: ResearchStageRunner

    def __post_init__(self) -> None:
        if not isinstance(self.stage_runner, ResearchStageRunner):
            raise TypeError("stage_runner 必须实现 ResearchStageRunner")


def build_research_graph(
    dependencies: ResearchGraphDependencies,
    checkpointer=None,
):
    """构建 Research 子图；不创建第二个 Harness 或外部执行循环。"""

    if not isinstance(dependencies, ResearchGraphDependencies):
        raise TypeError("dependencies 类型无效")
    graph = StateGraph(ResearchGraphState)

    def node(stage: ResearchStage):
        async def execute(state: ResearchGraphState) -> dict[str, object]:
            update = await dependencies.stage_runner.run_stage(stage, state)
            if not isinstance(update, ResearchStageUpdateV2):
                raise TypeError("RESEARCH_STAGE_UPDATE_INVALID")
            patch = _update_patch(update)
            patch["phase"] = stage
            patch["stage_events"] = [*state.get("stage_events", []), stage]
            if stage == "plan":
                if state.get("initial_collection_done", False):
                    patch["refill_rounds"] = state.get("refill_rounds", 0) + 1
                actions = patch.get("planned_action_ids")
                if actions == []:
                    patch["plan_exhausted"] = True
            if stage == "quality":
                patch.update(_quality_progress_patch(state, patch))
            if stage == "finalize":
                merged_state: dict[str, object] = dict(state)
                merged_state.update(patch)
                patch.update(_terminal_patch(cast(ResearchGraphState, merged_state)))
            return patch

        return execute

    stages: tuple[ResearchStage, ...] = (
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
    )
    for stage in stages:
        graph.add_node(stage, node(stage))
    graph.add_edge(START, "validate")
    graph.add_conditional_edges(
        "validate", lambda state: "finalize" if _control_stop(state) else "plan"
    )
    graph.add_conditional_edges("plan", _route_after_plan)
    pipeline = (
        ("discover", "acquire"),
        ("acquire", "normalize"),
        ("normalize", "filter"),
        ("filter", "deduplicate"),
        ("deduplicate", "cluster"),
        ("cluster", "claims"),
        ("claims", "quality"),
    )
    for current, following in pipeline:
        graph.add_conditional_edges(
            current,
            lambda state, next_stage=following: _route_collection_stage(
                state, next_stage
            ),
        )
    graph.add_conditional_edges("quality", _route_after_quality)
    graph.add_conditional_edges(
        "compose", lambda state: "finalize" if _control_stop(state) else "verify"
    )
    graph.add_conditional_edges("verify", _route_after_verify)
    graph.add_conditional_edges("render", lambda state: "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer or InMemorySaver())


def _update_patch(update: ResearchStageUpdateV2) -> dict[str, object]:
    patch: dict[str, object] = {}
    for field in update.model_fields_set:
        value = getattr(update, field)
        patch[field] = list(value) if isinstance(value, tuple) else value
    return patch


def _quality_progress_patch(
    state: ResearchGraphState,
    patch: dict[str, object],
) -> dict[str, object]:
    result: dict[str, object] = {"initial_collection_done": True}
    if not state.get("initial_collection_done", False):
        return result
    old_events = set(state.get("qualified_event_ids", []))
    old_claims = set(state.get("claim_ids", []))
    old_gaps = set(state.get("hard_gap_ids", []))
    new_events = set(
        cast(list[str], patch.get("qualified_event_ids", list(old_events)))
    )
    new_claims = set(cast(list[str], patch.get("claim_ids", list(old_claims))))
    new_gaps = set(cast(list[str], patch.get("hard_gap_ids", list(old_gaps))))
    gained = bool(new_events - old_events or new_claims - old_claims) or len(
        new_gaps
    ) < len(old_gaps)
    result["no_gain_rounds"] = 0 if gained else state.get("no_gain_rounds", 0) + 1
    return result


def _route_after_plan(state: ResearchGraphState) -> str:
    if _control_stop(state):
        return "finalize"
    if state.get("plan_exhausted") or not state.get("planned_action_ids"):
        return "compose" if state.get("qualified_event_ids") else "finalize"
    return _route_collection_stage(state, "discover")


def _route_collection_stage(state: ResearchGraphState, next_stage: str) -> str:
    if _control_stop(state):
        return "finalize"
    if state.get("budget_exhausted") or state.get("soft_deadline_reached"):
        return "compose" if state.get("qualified_event_ids") else "finalize"
    return next_stage


def _route_after_quality(state: ResearchGraphState) -> str:
    if _control_stop(state):
        return "finalize"
    if state.get("qualified_event_ids") and not state.get("hard_gap_ids"):
        return "compose"
    if state.get("complete_empty_plan"):
        return "compose"
    if _bounded_stop(state):
        return "compose" if state.get("qualified_event_ids") else "finalize"
    return "plan"


def _route_after_verify(state: ResearchGraphState) -> str:
    if _control_stop(state):
        return "finalize"
    if state.get("output_verified"):
        return "render"
    if state.get("output_recollect_requested") and not _bounded_stop(state):
        return "plan"
    return "finalize"


def _control_stop(state: ResearchGraphState) -> bool:
    return any(
        state.get(key, False)
        for key in ("cancelled", "fatal_error", "hard_deadline_reached")
    )


def _bounded_stop(state: ResearchGraphState) -> bool:
    return bool(
        state.get("soft_deadline_reached")
        or state.get("budget_exhausted")
        or state.get("no_gain_rounds", 0) >= 2
        or state.get("refill_rounds", 0) >= state.get("max_refill_rounds", 2)
        or state.get("plan_exhausted")
    )


def _terminal_patch(state: ResearchGraphState) -> dict[str, object]:
    stop_reason = _stop_reason(state)
    if state.get("cancelled") or state.get("hard_deadline_reached"):
        status = "NOT_EVALUATED"
    elif state.get("fatal_error"):
        status = "FAILED"
    else:
        status = stopped_research_status(
            len(state.get("qualified_event_ids", [])),
            len(state.get("hard_gap_ids", [])),
            state.get("complete_empty_plan", False),
            state.get("output_verified", False),
        )
        if status == "COMPLETE" and state.get("output_degraded"):
            status = "PARTIAL"
    return {"stop_reason": stop_reason, "domain_status": status}


def _stop_reason(state: ResearchGraphState) -> str:
    if state.get("cancelled"):
        return "USER_CANCELLED"
    if state.get("fatal_error"):
        return "FATAL_ERROR"
    if state.get("hard_deadline_reached"):
        return "HARD_DEADLINE"
    if state.get("output_degraded"):
        return "OUTPUT_DEGRADED"
    if (
        state.get("qualified_event_ids")
        and not state.get("hard_gap_ids")
        and state.get("output_verified")
    ):
        return "QUALITY_MET"
    if state.get("soft_deadline_reached"):
        return "SOFT_DEADLINE"
    if state.get("budget_exhausted"):
        return "BUDGET_LIMIT"
    if state.get("no_gain_rounds", 0) >= 2:
        return "NO_GAIN"
    if state.get("refill_rounds", 0) >= state.get("max_refill_rounds", 2):
        return "ROUND_LIMIT"
    return "PLAN_EXHAUSTED"


def stopped_research_status(
    accepted_count: int,
    hard_gaps: int,
    complete_empty_plan: bool,
    output_verified: bool,
) -> Literal["COMPLETE", "PARTIAL", "NO_MATCHES", "FAILED"]:
    if accepted_count > 0:
        if hard_gaps == 0 and output_verified:
            return "COMPLETE"
        return "PARTIAL"
    if complete_empty_plan:
        return "NO_MATCHES"
    return "FAILED"


__all__ = [
    "ResearchGraphDependencies",
    "ResearchStage",
    "ResearchStageRunner",
    "ResearchStageUpdateV2",
    "build_research_graph",
    "stopped_research_status",
]
