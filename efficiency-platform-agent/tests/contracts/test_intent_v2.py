"""意图 V2 契约的冻结行为测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.intent import (
    IntentEnvelopeV1,
    IntentRequirementsV1,
)
from efficiency_platform_agent.contracts.intent_v2 import (
    CapabilityPlanStepV2,
    CapabilityPlanV2,
    GoalNodeV2,
    IntentFrameV2,
    SourceSpan,
)
from tests.support.intent_v2_cases import intent_v2_case


def test_source_span_rejects_empty_or_reversed_unicode_range() -> None:
    with pytest.raises(ValidationError):
        SourceSpan(message_id="m-1", start=3, end=3, quoted_text="闻")


def test_intent_frame_rejects_negative_revision_and_more_than_eight_goals() -> None:
    base = {
        "task_id": "task-1",
        "message_id": "m-1",
        "anchor_time": datetime(2026, 9, 16, tzinfo=UTC),
        "timezone": "Asia/Shanghai",
        "dialog_act": "new_task",
    }
    with pytest.raises(ValidationError):
        IntentFrameV2(revision=-1, **base)
    goals = tuple(
        GoalNodeV2(goal_id=f"g-{index}", description="收集新闻")
        for index in range(9)
    )
    with pytest.raises(ValidationError):
        IntentFrameV2(revision=0, goal_nodes=goals, **base)


@pytest.mark.parametrize(
    "steps",
    [
        (
            CapabilityPlanStepV2(
                goal_id="g-1", capability_id="research", depends_on=("missing",)
            ),
        ),
        (
            CapabilityPlanStepV2(
                goal_id="g-1", capability_id="research", depends_on=("g-2",)
            ),
            CapabilityPlanStepV2(
                goal_id="g-2", capability_id="compose", depends_on=("g-1",)
            ),
        ),
    ],
)
def test_capability_plan_rejects_unknown_or_cyclic_dependency(
    steps: tuple[CapabilityPlanStepV2, ...],
) -> None:
    with pytest.raises(ValidationError):
        CapabilityPlanV2(steps=steps)


def test_v1_schema_digest_remains_frozen() -> None:
    import hashlib
    import json

    canonical = json.dumps(
        {
            "IntentEnvelopeV1": IntentEnvelopeV1.model_json_schema(),
            "IntentRequirementsV1": IntentRequirementsV1.model_json_schema(),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert hashlib.sha256(canonical.encode()).hexdigest() == (
        "db10e0986a65e8651a6faac0fc089203ca61096f5d8a6f53e9b476b53dbf7ef6"
    )


def test_unknown_intent_case_id_does_not_default_to_success() -> None:
    with pytest.raises(KeyError):
        intent_v2_case("missing-case")


def test_patch_rejects_unbounded_reference_items() -> None:
    from efficiency_platform_agent.contracts.intent_v2 import IntentPatchV2

    with pytest.raises(ValidationError):
        IntentPatchV2(
            base_revision=0,
            dialog_act="new_task",
            unresolved_references=("",),
        )
    with pytest.raises(ValidationError):
        IntentPatchV2(
            base_revision=0,
            dialog_act="new_task",
            unresolved_references=("x" * 513,),
        )
    with pytest.raises(ValidationError):
        IntentPatchV2(
            base_revision=0,
            dialog_act="new_task",
            unresolved_references=tuple(f"ref-{index}" for index in range(17)),
        )
