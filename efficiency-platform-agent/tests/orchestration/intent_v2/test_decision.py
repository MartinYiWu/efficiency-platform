"""I05 IntentDecisionPolicy 固定优先级测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from efficiency_platform_agent.contracts.intent_v2 import (
    CapabilityPlanStepV2,
    CapabilityPlanV2,
    GoalNodeV2,
    IntentAmbiguityV2,
    IntentFrameV2,
)
from efficiency_platform_agent.orchestration.intent_v2.decision import (
    IntentDecisionPolicyV2,
)


def _frame(
    *,
    dialog_act: str = "new_task",
    goals: tuple[GoalNodeV2, ...] = (),
    ambiguities: tuple[IntentAmbiguityV2, ...] = (),
    unresolved: tuple[str, ...] = (),
) -> IntentFrameV2:
    return IntentFrameV2(
        task_id="task-1",
        revision=0,
        message_id="m-1",
        anchor_time=datetime(2026, 9, 16, tzinfo=UTC),
        timezone="Asia/Shanghai",
        dialog_act=dialog_act,
        goal_nodes=goals,
        ambiguities=ambiguities,
        unresolved_references=unresolved,
    )


def test_technical_binding_error_is_failed_before_other_conditions() -> None:
    frame = _frame(unresolved=("它指什么",))
    decision = IntentDecisionPolicyV2().decide(
        frame,
        CapabilityPlanV2(supported=False, reason_codes=("CAPABILITY_SCHEMA_UNKNOWN",)),
    )

    assert decision.outcome == "FAILED"
    assert decision.reason_codes == ("CAPABILITY_SCHEMA_UNKNOWN",)
    assert decision.clarification_fields == ()


def test_unknown_or_unauthorized_capability_is_unsupported() -> None:
    frame = _frame(
        goals=(GoalNodeV2(goal_id="g-1", description="研究"),),
        unresolved=("它指什么",),
    )
    for reason in ("CAPABILITY_UNKNOWN", "CAPABILITY_UNAVAILABLE"):
        decision = IntentDecisionPolicyV2().decide(
            frame,
            CapabilityPlanV2(supported=False, reason_codes=(reason,)),
        )
        assert decision.outcome == "UNSUPPORTED"
        assert decision.reason_codes == (reason,)


def test_missing_required_field_clarifies_only_highest_priority_field() -> None:
    frame = _frame(
        goals=(GoalNodeV2(goal_id="g-1", description="研究"),),
        ambiguities=(
            IntentAmbiguityV2(
                field_name="source_constraints",
                candidates=("只看官方", "全部公开来源"),
                execution_impact="来源范围不同",
                blocking=True,
            ),
            IntentAmbiguityV2(
                field_name="temporal",
                candidates=("昨天", "最近24小时"),
                execution_impact="窗口不同",
                blocking=True,
            ),
        ),
    )
    decision = IntentDecisionPolicyV2().decide(
        frame,
        CapabilityPlanV2(
            supported=False,
            reason_codes=(
                "REQUIRED_FIELD_MISSING:output_requirements",
                "REQUIRED_FIELD_MISSING:topic",
            ),
        ),
    )

    assert decision.outcome == "CLARIFY"
    assert decision.clarification_fields == ("topic",)


def test_blocking_ambiguity_uses_temporal_before_source_and_only_one_question() -> None:
    frame = _frame(
        goals=(GoalNodeV2(goal_id="g-1", description="研究"),),
        ambiguities=(
            IntentAmbiguityV2(
                field_name="source_constraints",
                candidates=("官方", "全部"),
                execution_impact="来源不同",
                blocking=True,
            ),
            IntentAmbiguityV2(
                field_name="temporal",
                candidates=("上周", "最近7天"),
                execution_impact="时间不同",
                blocking=True,
            ),
        ),
    )
    decision = IntentDecisionPolicyV2().decide(
        frame,
        CapabilityPlanV2(
            steps=(CapabilityPlanStepV2(goal_id="g-1", capability_id="cap.x"),)
        ),
    )

    assert decision.outcome == "CLARIFY"
    assert decision.clarification_fields == ("temporal",)


def test_chat_without_business_goal_is_ready_but_executable_task_is_not() -> None:
    policy = IntentDecisionPolicyV2()
    ready = policy.decide(_frame(dialog_act="chat"), CapabilityPlanV2())
    clarify = policy.decide(_frame(dialog_act="new_task"), CapabilityPlanV2())

    assert ready.outcome == "READY"
    assert clarify.outcome == "CLARIFY"
    assert clarify.clarification_fields == ("goal",)


def test_fully_bound_plan_is_ready_without_confidence_threshold() -> None:
    frame = _frame(goals=(GoalNodeV2(goal_id="g-1", description="研究"),))
    decision = IntentDecisionPolicyV2().decide(
        frame,
        CapabilityPlanV2(
            steps=(CapabilityPlanStepV2(goal_id="g-1", capability_id="cap.x"),)
        ),
    )

    assert decision.outcome == "READY"
    assert decision.reason_codes == ()
    assert decision.clarification_fields == ()


def test_unknown_clarification_field_is_a_technical_failure() -> None:
    frame = _frame(
        goals=(GoalNodeV2(goal_id="g-1", description="研究"),),
        ambiguities=(
            IntentAmbiguityV2(
                field_name="tenant_id",
                candidates=("tenant-a", "tenant-b"),
                execution_impact="试图覆盖可信身份",
                blocking=True,
            ),
        ),
    )

    decision = IntentDecisionPolicyV2().decide(
        frame,
        CapabilityPlanV2(
            steps=(CapabilityPlanStepV2(goal_id="g-1", capability_id="cap.x"),)
        ),
    )

    assert decision.outcome == "FAILED"
    assert decision.reason_codes == ("INTENT_AMBIGUITY_FIELD_UNKNOWN",)
    assert decision.clarification_fields == ()
