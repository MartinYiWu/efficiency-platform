"""I05 确定性能力绑定与 DAG 测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.intent_v2 import (
    CapabilityCatalogSnapshot,
    CapabilityDescriptorV2,
    FieldValue,
    GoalNodeV2,
    IntentFrameV2,
    IntentParameterV2,
    PermissionSnapshotV2,
    SourceSpan,
)
from efficiency_platform_agent.orchestration.intent_v2.binding import (
    CapabilityBinderV2,
    CapabilityParameterSchemaRegistry,
    CapabilityParameterSchemaV2,
    ParameterRuleV2,
)


def _catalog(*ids: str) -> CapabilityCatalogSnapshot:
    return CapabilityCatalogSnapshot(
        catalog_version="catalog-1",
        capabilities=tuple(
            CapabilityDescriptorV2(
                capability_id=capability_id,
                version="1.0.0",
                description=capability_id,
                parameter_schema_ref=f"schema://{capability_id}",
            )
            for capability_id in ids
        ),
    )


def _schemas(
    *schemas: CapabilityParameterSchemaV2,
) -> CapabilityParameterSchemaRegistry:
    return CapabilityParameterSchemaRegistry(schemas)


def _frame(
    goals: tuple[GoalNodeV2, ...],
    *,
    topic: bool = True,
    dialog_act: str = "new_task",
) -> IntentFrameV2:
    return IntentFrameV2(
        task_id="task-1",
        revision=0,
        message_id="m-1",
        anchor_time=datetime(2026, 9, 16, tzinfo=UTC),
        timezone="Asia/Shanghai",
        dialog_act=dialog_act,
        goal_nodes=goals,
        topic=(
            FieldValue(
                value="AI 行业",
                origin="explicit",
                source_span=SourceSpan(
                    message_id="m-1", start=0, end=5, quoted_text="AI 行业"
                ),
            )
            if topic
            else None
        ),
    )


def test_unknown_candidate_never_falls_back_to_known_capability() -> None:
    binder = CapabilityBinderV2(
        _schemas(CapabilityParameterSchemaV2("schema://cap.known"))
    )
    frame = _frame(
        (
            GoalNodeV2(
                goal_id="g-1",
                description="研究",
                candidate_capability_ids=("cap.unknown", "cap.known"),
            ),
        )
    )

    plan = binder.bind(
        frame,
        _catalog("cap.known"),
        PermissionSnapshotV2(version="p-1", allowed_capability_ids=("cap.known",)),
    )

    assert plan.supported is False
    assert plan.steps == ()
    assert plan.reason_codes == ("CAPABILITY_UNKNOWN",)


def test_unauthorized_capability_returns_no_partial_plan() -> None:
    binder = CapabilityBinderV2(
        _schemas(CapabilityParameterSchemaV2("schema://cap.research"))
    )
    frame = _frame(
        (
            GoalNodeV2(
                goal_id="g-1",
                description="研究",
                candidate_capability_ids=("cap.research",),
            ),
        )
    )

    plan = binder.bind(
        frame,
        _catalog("cap.research"),
        PermissionSnapshotV2(version="p-1"),
    )

    assert plan.supported is False
    assert plan.steps == ()
    assert plan.reason_codes == ("CAPABILITY_UNAVAILABLE",)


def test_later_invalid_goal_discards_every_previously_valid_goal() -> None:
    binder = CapabilityBinderV2(
        _schemas(
            CapabilityParameterSchemaV2("schema://cap.valid"),
            CapabilityParameterSchemaV2("schema://cap.invalid"),
        )
    )
    frame = _frame(
        (
            GoalNodeV2(
                goal_id="g-valid",
                description="先研究",
                candidate_capability_ids=("cap.valid",),
            ),
            GoalNodeV2(
                goal_id="g-invalid",
                description="再处理",
                candidate_capability_ids=("cap.invalid",),
                parameters=(
                    IntentParameterV2(name="tenant_id", value="tenant-attack"),
                ),
            ),
        )
    )

    plan = binder.bind(
        frame,
        _catalog("cap.valid", "cap.invalid"),
        PermissionSnapshotV2(
            version="p-1",
            allowed_capability_ids=("cap.valid", "cap.invalid"),
        ),
    )

    assert plan.supported is False
    assert plan.steps == ()
    assert plan.reason_codes == ("CAPABILITY_PARAMETER_INVALID",)


def test_parameter_schema_rejects_unknown_and_wrong_strict_type() -> None:
    schema = CapabilityParameterSchemaV2(
        "schema://cap.research",
        parameter_rules=(ParameterRuleV2("count", "integer"),),
    )
    binder = CapabilityBinderV2(_schemas(schema))
    catalog = _catalog("cap.research")
    permissions = PermissionSnapshotV2(
        version="p-1", allowed_capability_ids=("cap.research",)
    )
    for parameter in (
        IntentParameterV2(name="tenant_id", value="tenant-attack"),
        IntentParameterV2(name="count", value="3"),
        IntentParameterV2(name="count", value=True),
    ):
        frame = _frame(
            (
                GoalNodeV2(
                    goal_id="g-1",
                    description="研究",
                    candidate_capability_ids=("cap.research",),
                    parameters=(parameter,),
                ),
            )
        )

        plan = binder.bind(frame, catalog, permissions)

        assert plan.supported is False
        assert plan.steps == ()
        assert plan.reason_codes == ("CAPABILITY_PARAMETER_INVALID",)


def test_missing_required_frame_field_is_explicit_and_non_executable() -> None:
    binder = CapabilityBinderV2(
        _schemas(
            CapabilityParameterSchemaV2(
                "schema://cap.research", required_frame_fields=("topic",)
            )
        )
    )
    frame = _frame(
        (
            GoalNodeV2(
                goal_id="g-1",
                description="研究",
                candidate_capability_ids=("cap.research",),
            ),
        ),
        topic=False,
    )

    plan = binder.bind(
        frame,
        _catalog("cap.research"),
        PermissionSnapshotV2(version="p-1", allowed_capability_ids=("cap.research",)),
    )

    assert plan.supported is False
    assert plan.steps == ()
    assert plan.reason_codes == ("REQUIRED_FIELD_MISSING:topic",)


def test_successful_plan_uses_stable_topological_order_and_dependencies() -> None:
    ids = ("cap.research", "cap.quality", "cap.content")
    binder = CapabilityBinderV2(
        _schemas(*(CapabilityParameterSchemaV2(f"schema://{item}") for item in ids))
    )
    frame = _frame(
        (
            GoalNodeV2(
                goal_id="g-content",
                description="写作",
                candidate_capability_ids=("cap.content",),
                depends_on=("g-quality",),
            ),
            GoalNodeV2(
                goal_id="g-research",
                description="研究",
                candidate_capability_ids=("cap.research",),
            ),
            GoalNodeV2(
                goal_id="g-quality",
                description="筛选",
                candidate_capability_ids=("cap.quality",),
                depends_on=("g-research",),
            ),
        )
    )

    plan = binder.bind(
        frame,
        _catalog(*ids),
        PermissionSnapshotV2(version="p-1", allowed_capability_ids=ids),
    )

    assert plan.supported is True
    assert tuple(step.goal_id for step in plan.steps) == (
        "g-research",
        "g-quality",
        "g-content",
    )
    assert plan.steps[-1].depends_on == ("g-quality",)


def test_frame_contract_rejects_cycles_and_more_than_eight_goals_before_binding() -> (
    None
):
    with pytest.raises(ValidationError):
        _frame(
            (
                GoalNodeV2(goal_id="g-1", description="一", depends_on=("g-2",)),
                GoalNodeV2(goal_id="g-2", description="二", depends_on=("g-1",)),
            )
        )
    with pytest.raises(ValidationError):
        _frame(
            tuple(
                GoalNodeV2(goal_id=f"g-{index}", description="目标")
                for index in range(9)
            )
        )
