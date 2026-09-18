"""I06 ResearchBrief、场景投影与缓存复用测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)
from efficiency_platform_agent.contracts.intent_v2 import (
    CapabilityPlanStepV2,
    CapabilityPlanV2,
    EntityV2,
    FieldValue,
    GoalNodeV2,
    IntentAmbiguityV2,
    IntentFrameV2,
    IntentParameterV2,
    OutputRequirementsV2,
    SourceConstraintsV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    ResearchPolicySnapshotV2,
    TrustedResearchContextV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import (
    CalendarPeriodExpression,
    ResolvedTimeWindow,
)
from efficiency_platform_agent.orchestration.intent_v2.research_bridge import (
    EvidenceReusePolicyV2,
    ResearchBridgeError,
    ResearchBriefBuilderV2,
    ResearchCacheEntryV2,
)
from efficiency_platform_agent.orchestration.intent_v2.scenario_adapter import (
    ScenarioInputAdapter,
)

ANCHOR = datetime.fromisoformat("2026-09-16T09:41:00+08:00")
RESEARCH = OperationSpecialistCapabilityId.RESEARCH_INSIGHT.value
CONTENT = OperationSpecialistCapabilityId.CHANNEL_CONTENT.value


def _derived(value: object) -> FieldValue[object]:
    return FieldValue(value=value, origin="derived", normalizer_version="test/1")


def _frame(
    *,
    source_ids: tuple[str, ...] = ("xiaohongshu",),
    targets: tuple[str, ...] = ("wechat_official_account",),
    count: int | None = 3,
    temporal: bool = True,
    exclusions: tuple[str, ...] = ("融资",),
    ambiguities: tuple[IntentAmbiguityV2, ...] = (),
    unresolved: tuple[str, ...] = (),
) -> IntentFrameV2:
    research_parameters = (
        (IntentParameterV2(name="count", value=count),) if count is not None else ()
    )
    return IntentFrameV2(
        task_id="task-1",
        revision=2,
        message_id="m-2",
        anchor_time=ANCHOR,
        timezone="Asia/Shanghai",
        dialog_act="new_task",
        goal_nodes=(
            GoalNodeV2(
                goal_id="g-research",
                description="研究 AI 动态",
                candidate_capability_ids=(RESEARCH,),
                parameters=research_parameters,
            ),
            GoalNodeV2(
                goal_id="g-content",
                description="写成公众号",
                candidate_capability_ids=(CONTENT,),
                depends_on=("g-research",),
            ),
        ),
        topic=_derived("AI 行业动态"),
        entities=_derived(
            (EntityV2(raw_text="OpenAI", canonical_name="OpenAI", role="company"),)
        ),
        exclusions=_derived(exclusions),
        temporal=(
            _derived(CalendarPeriodExpression(text="昨天", period="day", offset=-1))
            if temporal
            else None
        ),
        source_constraints=_derived(
            SourceConstraintsV2(allowed_source_ids=source_ids, languages=("zh",))
        ),
        output_requirements=_derived(
            OutputRequirementsV2(
                output_types=("article",),
                target_platforms=targets,
                language="zh-CN",
            )
        ),
        ambiguities=ambiguities,
        unresolved_references=unresolved,
    )


def _context(*, tenant_id: str = "tenant-1") -> TrustedResearchContextV2:
    return TrustedResearchContextV2(
        tenant_id=tenant_id,
        run_id="run-1",
        task_id="task-1",
        budget_lease_id="lease-1",
    )


def _policy() -> ResearchPolicySnapshotV2:
    return ResearchPolicySnapshotV2(
        quality_policy_id="research-quality-v2",
        policy_version="2026-09-16",
    )


def _build(frame: IntentFrameV2 | None = None):
    return ResearchBriefBuilderV2().build(frame or _frame(), _context(), _policy())


def test_bridge_preserves_source_destination_count_exclusions_and_time() -> None:
    brief = _build()

    assert brief.source_constraints.allowed_source_ids == ("xiaohongshu",)
    assert brief.output_requirements.target_platforms == ("wechat_official_account",)
    assert brief.count_policy.mode == "exact"
    assert brief.count_policy.target == 3
    assert brief.count_policy.minimum == 3
    assert brief.exclusions == ("融资",)
    assert brief.intent_scope_hash == _frame().scope_hash
    assert brief.time_window.start.isoformat() == "2026-09-14T16:00:00+00:00"
    assert brief.time_window.end.isoformat() == "2026-09-15T16:00:00+00:00"
    assert {item.dimension for item in brief.hard_requirements} == {
        "topic",
        "time_window",
        "source_constraints",
        "output_requirements",
        "count_policy",
        "exclusions",
    }


def test_unknown_source_is_preserved_and_default_count_is_auditable() -> None:
    brief = _build(_frame(source_ids=("unknown-public-source",), count=None))

    assert brief.source_constraints.allowed_source_ids == ("unknown-public-source",)
    assert brief.count_policy.mode == "best_effort"
    assert brief.count_policy.target == 5
    assert "DEFAULT_COUNT_POLICY:best_effort:5:1" in brief.diagnostics


@pytest.mark.parametrize(
    ("frame", "context", "error_code"),
    [
        (_frame(temporal=False), _context(), "RESEARCH_TIME_REQUIRED"),
        (
            _frame(unresolved=("它指什么",)),
            _context(),
            "INTENT_NOT_READY",
        ),
        (
            _frame(
                ambiguities=(
                    IntentAmbiguityV2(
                        field_name="temporal",
                        candidates=("昨天", "24小时"),
                        execution_impact="窗口不同",
                        blocking=True,
                    ),
                )
            ),
            _context(),
            "INTENT_NOT_READY",
        ),
        (_frame(), _context(tenant_id="tenant-2"), "TRUSTED_TASK_MISMATCH"),
    ],
)
def test_bridge_rejects_non_ready_or_untrusted_input(
    frame: IntentFrameV2,
    context: TrustedResearchContextV2,
    error_code: str,
) -> None:
    if error_code == "TRUSTED_TASK_MISMATCH":
        context = context.model_copy(update={"task_id": "other-task"})
    with pytest.raises(ResearchBridgeError) as caught:
        ResearchBriefBuilderV2().build(frame, context, _policy())

    assert caught.value.code == error_code


def test_hard_requirement_ids_and_digest_are_stable_but_revision_sensitive() -> None:
    first = _build()
    second = _build()
    changed_revision = _build(_frame().model_copy(update={"revision": 3}))

    assert first.hard_requirements == second.hard_requirements
    assert first.canonical_digest() == second.canonical_digest()
    assert first.canonical_digest() != changed_revision.canonical_digest()

    tampered = first.model_dump()
    tampered["hard_requirements"][0]["value_digest"] = "0" * 64
    with pytest.raises(ValidationError):
        type(first).model_validate(tampered)


def test_bridge_rejects_ambiguous_research_candidate_and_zero_revision() -> None:
    frame = _frame()
    research_goal = frame.goal_nodes[0].model_copy(
        update={"candidate_capability_ids": (RESEARCH, CONTENT)}
    )
    ambiguous = frame.model_copy(
        update={"goal_nodes": (research_goal, frame.goal_nodes[1])}
    )
    with pytest.raises(ResearchBridgeError) as caught:
        _build(ambiguous)
    assert caught.value.code == "RESEARCH_GOAL_AMBIGUOUS"

    with pytest.raises(ResearchBridgeError) as caught:
        _build(frame.model_copy(update={"revision": 0}))
    assert caught.value.code == "INTENT_NOT_READY"


def test_scenario_projection_keeps_each_goal_dependency_and_parameters() -> None:
    frame = _frame()
    plan = CapabilityPlanV2(
        steps=(
            CapabilityPlanStepV2(goal_id="g-research", capability_id=RESEARCH),
            CapabilityPlanStepV2(
                goal_id="g-content",
                capability_id=CONTENT,
                depends_on=("g-research",),
            ),
        )
    )

    projection = ScenarioInputAdapter().project(frame, plan)

    assert projection.supported is True
    assert tuple(step.goal_id for step in projection.steps) == (
        "g-research",
        "g-content",
    )
    assert projection.steps[1].depends_on == ("g-research",)
    assert projection.steps[0].parameters.intent_parameters[0].name == "count"
    assert projection.steps[0].parameters.source_constraints.allowed_source_ids == (
        "xiaohongshu",
    )
    assert projection.steps[1].parameters.output_requirements.target_platforms == (
        "wechat_official_account",
    )


def test_scenario_projection_rejects_incomplete_plan_without_partial_steps() -> None:
    projection = ScenarioInputAdapter().project(
        _frame(),
        CapabilityPlanV2(
            steps=(CapabilityPlanStepV2(goal_id="g-research", capability_id=RESEARCH),)
        ),
    )

    assert projection.supported is False
    assert projection.reason_codes == ("SCENARIO_PLAN_INCOMPLETE",)
    assert projection.steps == ()


def test_scenario_projection_rejects_non_ready_dependency_or_unknown_capability() -> (
    None
):
    adapter = ScenarioInputAdapter()
    frame = _frame(unresolved=("它指什么",))
    complete = CapabilityPlanV2(
        steps=(
            CapabilityPlanStepV2(goal_id="g-research", capability_id=RESEARCH),
            CapabilityPlanStepV2(
                goal_id="g-content",
                capability_id=CONTENT,
                depends_on=("g-research",),
            ),
        )
    )
    assert adapter.project(frame, complete).reason_codes == (
        "SCENARIO_INTENT_NOT_READY",
    )

    dependency_lost = CapabilityPlanV2(
        steps=(
            CapabilityPlanStepV2(goal_id="g-research", capability_id=RESEARCH),
            CapabilityPlanStepV2(goal_id="g-content", capability_id=CONTENT),
        )
    )
    assert adapter.project(_frame(), dependency_lost).reason_codes == (
        "SCENARIO_DEPENDENCY_MISMATCH",
    )

    unknown_goal = (
        _frame()
        .goal_nodes[0]
        .model_copy(update={"candidate_capability_ids": ("operation.unknown",)})
    )
    unknown_frame = _frame().model_copy(
        update={"goal_nodes": (unknown_goal, _frame().goal_nodes[1])}
    )
    unknown_plan = CapabilityPlanV2(
        steps=(
            CapabilityPlanStepV2(
                goal_id="g-research", capability_id="operation.unknown"
            ),
            CapabilityPlanStepV2(
                goal_id="g-content",
                capability_id=CONTENT,
                depends_on=("g-research",),
            ),
        )
    )
    result = adapter.project(unknown_frame, unknown_plan)
    assert result.supported is False
    assert result.reason_codes == ("SCENARIO_CAPABILITY_UNSUPPORTED",)
    assert result.steps == ()


def _cache_entry(brief, **changes: object) -> ResearchCacheEntryV2:
    base = ResearchCacheEntryV2(
        cache_entry_id="cache-1",
        tenant_id="tenant-1",
        permission_snapshot_version="permission-1",
        topic_digest=EvidenceReusePolicyV2.topic_digest(brief.topic),
        entities=brief.entities,
        exclusions=brief.exclusions,
        covered_time_window=brief.time_window,
        source_ids=("xiaohongshu",),
        languages=("zh",),
        event_regions=(),
        publisher_regions=(),
        primary_only=False,
        expires_at=datetime(2026, 9, 16, 8, 0, tzinfo=UTC),
    )
    return base.model_copy(update=changes)


def test_cache_reuse_allows_output_only_change_but_rejects_new_time() -> None:
    original = _build()
    output_changed = _build(_frame(targets=("xiaohongshu",)))
    cache = _cache_entry(original)
    policy = EvidenceReusePolicyV2()
    now = datetime(2026, 9, 16, 2, 0, tzinfo=UTC)

    assert (
        policy.evaluate(
            cache,
            output_changed,
            tenant_id="tenant-1",
            permission_snapshot_version="permission-1",
            now=now,
        ).reusable
        is True
    )
    shifted = original.model_copy(
        update={
            "time_window": ResolvedTimeWindow(
                start=original.time_window.start - timedelta(days=1),
                end=original.time_window.end,
                timezone=original.time_window.timezone,
                precision="day",
                anchor=original.time_window.anchor,
                basis=original.time_window.basis,
            )
        }
    )
    rejected = policy.evaluate(
        cache,
        shifted,
        tenant_id="tenant-1",
        permission_snapshot_version="permission-1",
        now=now,
    )

    assert rejected.reusable is False
    assert rejected.reason_codes == ("CACHE_TIME_NOT_COVERED",)


@pytest.mark.parametrize(
    ("changes", "tenant", "permission", "now", "reason"),
    [
        (
            {},
            "tenant-2",
            "permission-1",
            datetime(2026, 9, 16, 2, tzinfo=UTC),
            "CACHE_TENANT_MISMATCH",
        ),
        (
            {},
            "tenant-1",
            "permission-2",
            datetime(2026, 9, 16, 2, tzinfo=UTC),
            "CACHE_PERMISSION_MISMATCH",
        ),
        (
            {},
            "tenant-1",
            "permission-1",
            datetime(2026, 9, 16, 9, tzinfo=UTC),
            "CACHE_EXPIRED",
        ),
        (
            {"source_ids": ("other",)},
            "tenant-1",
            "permission-1",
            datetime(2026, 9, 16, 2, tzinfo=UTC),
            "CACHE_SOURCE_MISMATCH",
        ),
    ],
)
def test_cache_reuse_fails_closed_on_trust_or_source_mismatch(
    changes: dict[str, object],
    tenant: str,
    permission: str,
    now: datetime,
    reason: str,
) -> None:
    brief = _build()
    decision = EvidenceReusePolicyV2().evaluate(
        _cache_entry(brief, **changes),
        brief,
        tenant_id=tenant,
        permission_snapshot_version=permission,
        now=now,
    )

    assert decision.reusable is False
    assert decision.reason_codes == (reason,)


def test_cache_reuse_rejects_changed_entity_scope() -> None:
    brief = _build()
    decision = EvidenceReusePolicyV2().evaluate(
        _cache_entry(brief, entities=("Other Company",)),
        brief,
        tenant_id="tenant-1",
        permission_snapshot_version="permission-1",
        now=datetime(2026, 9, 16, 2, tzinfo=UTC),
    )

    assert decision.reusable is False
    assert decision.reason_codes == ("CACHE_TOPIC_MISMATCH",)
