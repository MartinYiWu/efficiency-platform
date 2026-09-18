"""Intent V2 多轮 Reducer 的确定性行为测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import pytest

from efficiency_platform_agent.contracts.intent_v2 import (
    FieldValue,
    IntentFrameV2,
    OutputRequirementsV2,
    SourceSpan,
    TrustedMessageV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import CalendarPeriodExpression
from efficiency_platform_agent.orchestration.intent_v2.patch_validation import (
    IntentPatchValidator,
    TrustedIntentScope,
    ValidatedIntentPatch,
)
from efficiency_platform_agent.orchestration.intent_v2.reducer import (
    IntentReductionError,
    IntentStateReducer,
)


def span(message_id: str, quote: str = "改") -> SourceSpan:
    return SourceSpan(
        message_id=message_id,
        start=0,
        end=len(quote),
        quoted_text=quote,
    )


def explicit[T](value: T, message_id: str = "m-1", quote: str = "旧") -> FieldValue[T]:
    return FieldValue(value=value, origin="explicit", source_span=span(message_id, quote))


def message(
    message_id: str = "m-2",
    *,
    task_id: str = "task-1",
    text: str = "改",
    received_at: str = "2026-09-16T09:41:00+08:00",
    timezone: str = "Asia/Shanghai",
    referenced_task_ids: tuple[str, ...] = (),
) -> TrustedMessageV2:
    return TrustedMessageV2(
        task_id=task_id,
        message_id=message_id,
        text=text,
        received_at=datetime.fromisoformat(received_at),
        timezone=timezone,
        referenced_task_ids=referenced_task_ids,
    )


def previous_frame() -> IntentFrameV2:
    return IntentFrameV2(
        task_id="task-1",
        revision=1,
        message_id="m-1",
        anchor_time=datetime.fromisoformat("2026-09-15T08:00:00+08:00"),
        timezone="Asia/Shanghai",
        dialog_act="new_task",
        topic=explicit("AI 行业"),
        exclusions=explicit(("融资",)),
        temporal=explicit(
            CalendarPeriodExpression(
                text="昨天", period="day", offset=-1
            )
        ),
        output_requirements=explicit(
            OutputRequirementsV2(
                output_types=("digest",),
                target_platforms=("wechat", "xiaohongshu"),
                language="zh-CN",
            )
        ),
    )


def validated_patch(
    *operations: dict[str, object],
    base_revision: int = 1,
    dialog_act: Literal[
        "new_task",
        "answer_clarification",
        "refine",
        "follow_up",
        "cancel",
        "resume",
        "chat",
    ] = "refine",
    task_id: str = "task-1",
    message_id: str = "m-2",
    text: str = "改",
    goal_updates: list[dict[str, object]] | None = None,
) -> ValidatedIntentPatch:
    result = IntentPatchValidator().validate(
        {
            "base_revision": base_revision,
            "dialog_act": dialog_act,
            "goal_updates": goal_updates or [],
            "field_operations": list(operations),
        },
        {message_id: text},
        TrustedIntentScope(
            task_id=task_id,
            current_message_id=message_id,
            user_message_ids=frozenset({message_id}),
            visible_revisions=frozenset({0, 1, 2}),
        ),
    )
    assert result.is_valid, result.reason_code
    return result


def explicit_operation(
    field_name: str,
    value: object,
    *,
    operation: str = "set",
    message_id: str = "m-2",
    quote: str = "改",
) -> dict[str, object]:
    return {
        "operation": operation,
        "field_name": field_name,
        "value": {
            "value": value,
            "origin": "explicit",
            "source_span": {
                "message_id": message_id,
                "start": 0,
                "end": len(quote),
                "quoted_text": quote,
            },
        },
    }


def clear_operation(field_name: str) -> dict[str, object]:
    return {
        "operation": "clear",
        "field_name": field_name,
        "source_span": {
            "message_id": "m-2",
            "start": 0,
            "end": 1,
            "quoted_text": "改",
        },
    }


def default_operation(
    field_name: str,
    value: object,
    *,
    operation: str = "set",
    policy_id: str = "defaults/1",
) -> dict[str, object]:
    return {
        "operation": operation,
        "field_name": field_name,
        "value": {
            "value": value,
            "origin": "default",
            "default_policy_id": policy_id,
        },
    }


def validated_default_patch(
    *operations: dict[str, object],
    base_revision: int = 1,
    message_id: str = "m-2",
) -> ValidatedIntentPatch:
    result = IntentPatchValidator().validate(
        {
            "base_revision": base_revision,
            "dialog_act": "refine",
            "field_operations": list(operations),
        },
        {message_id: "改"},
        TrustedIntentScope(
            task_id="task-1",
            current_message_id=message_id,
            user_message_ids=frozenset({message_id}),
            visible_revisions=frozenset({0, 1, 2}),
            allowed_default_policy_ids=frozenset({"defaults/1"}),
        ),
    )
    assert result.is_valid, result.reason_code
    return result


def test_refine_keeps_topic_and_removes_only_target_platform() -> None:
    old = previous_frame()
    patch = validated_patch(
        explicit_operation(
            "target_platforms", ["wechat"], operation="remove"
        )
    )

    result = IntentStateReducer().apply(old, patch, message())

    assert result.topic is not None and result.topic.value == "AI 行业"
    assert result.output_requirements is not None
    assert result.output_requirements.value is not None
    assert result.output_requirements.value.target_platforms == ("xiaohongshu",)
    assert result.revision == 2
    assert old.revision == 1
    assert old.output_requirements is not None
    assert old.output_requirements.value is not None
    assert old.output_requirements.value.target_platforms == (
        "wechat",
        "xiaohongshu",
    )
    assert result.scope_hash != old.scope_hash


def test_refine_replaces_topic_without_changing_time_or_output() -> None:
    old = previous_frame()
    patch = validated_patch(explicit_operation("topic", "新能源"))

    result = IntentStateReducer().apply(old, patch, message())

    assert result.topic is not None and result.topic.value == "新能源"
    assert result.temporal == old.temporal
    assert result.output_requirements == old.output_requirements
    assert result.anchor_time == old.anchor_time
    assert result.scope_hash != old.scope_hash


def test_new_task_does_not_inherit_old_research_slots() -> None:
    old = previous_frame()
    patch = validated_patch(
        explicit_operation("topic", "招聘文案"),
        base_revision=0,
        dialog_act="new_task",
        task_id="task-2",
    )

    result = IntentStateReducer().apply(
        old,
        patch,
        message(task_id="task-2"),
    )

    assert result.task_id == "task-2"
    assert result.revision == 1
    assert result.topic is not None and result.topic.value == "招聘文案"
    assert result.temporal is None
    assert result.exclusions is None
    assert result.output_requirements is None


def test_default_or_derived_value_cannot_overwrite_explicit_topic() -> None:
    old = previous_frame()
    for value in (
        {
            "value": "默认主题",
            "origin": "default",
            "default_policy_id": "topic-default/1",
        },
        {
            "value": "派生主题",
            "origin": "derived",
            "normalizer_version": "topic-normalizer/1",
        },
    ):
        result = IntentPatchValidator().validate(
            {
                "base_revision": 1,
                "dialog_act": "refine",
                "field_operations": [
                    {"operation": "set", "field_name": "topic", "value": value}
                ],
            },
            {"m-2": "改"},
            TrustedIntentScope(
                task_id="task-1",
                current_message_id="m-2",
                user_message_ids=frozenset({"m-2"}),
                visible_revisions=frozenset({1}),
                allowed_default_policy_ids=frozenset({"topic-default/1"}),
                allowed_normalizer_versions=frozenset({"topic-normalizer/1"}),
            ),
        )
        assert result.is_valid
        frame = IntentStateReducer().apply(old, result, message())
        assert frame.topic == old.topic


def test_collection_append_remove_is_stable_and_does_not_replace_other_values() -> None:
    old = previous_frame()
    patch = validated_patch(
        explicit_operation("exclusions", ["广告", "融资"], operation="append"),
        explicit_operation("exclusions", ["融资"], operation="remove"),
    )

    result = IntentStateReducer().apply(old, patch, message())

    assert result.exclusions is not None
    assert result.exclusions.value == ("广告",)
    assert result.topic == old.topic


def test_revision_conflict_is_explicit_and_duplicate_message_is_idempotent() -> None:
    old = previous_frame()
    patch = validated_patch(explicit_operation("topic", "新能源"))
    first = IntentStateReducer().apply(old, patch, message())

    assert IntentStateReducer().apply(first, patch, message()) is first
    concurrent = validated_patch(
        explicit_operation("topic", "机器人", message_id="m-3"),
        message_id="m-3",
    )
    with pytest.raises(IntentReductionError, match="INTENT_REVISION_CONFLICT") as exc:
        IntentStateReducer().apply(first, concurrent, message(message_id="m-3"))
    assert exc.value.code == "INTENT_REVISION_CONFLICT"


def test_cross_task_refine_is_rejected() -> None:
    with pytest.raises(IntentReductionError, match="INTENT_TASK_MISMATCH"):
        IntentStateReducer().apply(
            previous_frame(),
            validated_patch(explicit_operation("topic", "新能源")),
            message(task_id="task-other"),
        )


def test_explicit_temporal_change_uses_trusted_message_anchor() -> None:
    patch = validated_patch(
        explicit_operation(
            "temporal",
            {
                "kind": "calendar_period",
                "text": "上周",
                "period": "week",
                "offset": -1,
            },
        )
    )
    trusted = message(received_at="2026-09-17T10:00:00+08:00")

    result = IntentStateReducer().apply(previous_frame(), patch, trusted)

    assert result.anchor_time == trusted.received_at
    assert result.timezone == trusted.timezone
    assert result.temporal is not None
    assert result.temporal.value is not None
    assert result.temporal.value.text == "上周"


def test_same_relative_time_with_new_anchor_invalidates_scope_hash() -> None:
    patch = validated_patch(
        explicit_operation(
            "temporal",
            {
                "kind": "calendar_period",
                "text": "昨天",
                "period": "day",
                "offset": -1,
            },
        )
    )
    result = IntentStateReducer().apply(
        previous_frame(),
        patch,
        message(received_at="2026-09-17T10:00:00+08:00"),
    )
    assert result.temporal is not None
    assert result.temporal.value is not None
    assert result.temporal.value.text == "昨天"
    assert result.scope_hash != previous_frame().scope_hash


def test_explicit_temporal_change_uses_current_trusted_timezone() -> None:
    patch = validated_patch(
        explicit_operation(
            "temporal",
            {
                "kind": "calendar_period",
                "text": "昨天",
                "period": "day",
                "offset": -1,
            },
        )
    )
    result = IntentStateReducer().apply(
        previous_frame(),
        patch,
        message(
            received_at="2026-09-16T09:41:00-04:00",
            timezone="America/New_York",
        ),
    )
    assert result.timezone == "America/New_York"
    assert result.anchor_time.utcoffset() != previous_frame().anchor_time.utcoffset()
    assert result.scope_hash != previous_frame().scope_hash


def test_invalid_validated_patch_cannot_enter_reducer() -> None:
    invalid = ValidatedIntentPatch(
        patch=None,
        error_code="INTENT_SCHEMA_INVALID",
        reason_code="SOURCE_SPAN_MISMATCH",
    )
    with pytest.raises(IntentReductionError, match="INTENT_SCHEMA_INVALID"):
        IntentStateReducer().apply(previous_frame(), invalid, message())


def test_explicit_clear_is_distinct_from_unmentioned_field() -> None:
    old = previous_frame()
    result = IntentStateReducer().apply(
        old,
        validated_patch(clear_operation("topic")),
        message(),
    )
    assert result.topic is None
    assert result.temporal == old.temporal


def test_same_semantic_value_keeps_scope_hash_despite_new_provenance() -> None:
    old = previous_frame()
    result = IntentStateReducer().apply(
        old,
        validated_patch(explicit_operation("topic", "AI 行业")),
        message(),
    )
    assert result.revision == 2
    assert result.topic != old.topic
    assert result.scope_hash == old.scope_hash


def test_source_leaf_update_preserves_other_business_fields() -> None:
    old = previous_frame()
    result = IntentStateReducer().apply(
        old,
        validated_patch(
            explicit_operation("event_regions", ["CN"], operation="append")
        ),
        message(),
    )
    assert result.source_constraints is not None
    assert result.source_constraints.value is not None
    assert result.source_constraints.value.event_regions == ("CN",)
    assert result.output_requirements == old.output_requirements
    assert result.topic == old.topic


def test_goal_updates_are_stable_upserts_not_whole_list_replacement() -> None:
    old_payload = previous_frame().model_dump(exclude={"scope_hash"})
    old_payload["goal_nodes"] = [
        {"goal_id": "g-1", "description": "收集新闻"}
    ]
    old = IntentFrameV2.model_validate(old_payload)
    patch = validated_patch(
        goal_updates=[
            {"goal_id": "g-1", "description": "收集并核验新闻"},
            {"goal_id": "g-2", "description": "生成摘要", "depends_on": ["g-1"]},
        ]
    )
    result = IntentStateReducer().apply(old, patch, message())
    assert tuple(goal.goal_id for goal in result.goal_nodes) == ("g-1", "g-2")
    assert result.goal_nodes[0].description == "收集并核验新闻"


def test_patch_cannot_be_rebound_to_an_unvalidated_message() -> None:
    patch = validated_patch(explicit_operation("topic", "新能源"))
    with pytest.raises(IntentReductionError, match="INTENT_PATCH_CONTEXT_MISMATCH"):
        IntentStateReducer().apply(
            previous_frame(),
            patch,
            message(message_id="m-other"),
        )


def test_patch_is_bound_to_current_message_not_only_visible_history() -> None:
    result = IntentPatchValidator().validate(
        {
            "base_revision": 1,
            "dialog_act": "refine",
            "field_operations": [
                {
                    "operation": "set",
                    "field_name": "topic",
                    "value": {
                        "value": "甲",
                        "origin": "explicit",
                        "source_span": {
                            "message_id": "m-a",
                            "start": 0,
                            "end": 1,
                            "quoted_text": "甲",
                        },
                    },
                }
            ],
        },
        {"m-a": "甲", "m-b": "乙"},
        TrustedIntentScope(
            task_id="task-1",
            current_message_id="m-a",
            user_message_ids=frozenset({"m-a", "m-b"}),
            visible_revisions=frozenset({1}),
        ),
    )
    assert result.is_valid
    with pytest.raises(IntentReductionError, match="INTENT_PATCH_CONTEXT_MISMATCH"):
        IntentStateReducer().apply(
            previous_frame(),
            result,
            message(message_id="m-b", text="乙"),
        )


def test_clear_required_output_language_returns_stable_state_error() -> None:
    with pytest.raises(IntentReductionError, match="INTENT_CLEAR_REQUIRED_FIELD"):
        IntentStateReducer().apply(
            previous_frame(),
            validated_patch(clear_operation("output_language")),
            message(),
        )


def test_frame_scope_hash_round_trips_and_rejects_tampering() -> None:
    frame = previous_frame()
    restored = IntentFrameV2.model_validate(frame.model_dump())
    assert restored == frame
    payload = frame.model_dump()
    payload["scope_hash"] = "0" * 64
    with pytest.raises(ValueError, match="SCOPE_HASH_MISMATCH"):
        IntentFrameV2.model_validate(payload)


def test_scope_hash_canonicalizes_anchor_to_the_same_instant() -> None:
    local = previous_frame()
    payload = local.model_dump(exclude={"scope_hash"})
    payload["anchor_time"] = local.anchor_time.astimezone(UTC)
    utc = IntentFrameV2.model_validate(payload)
    assert utc.anchor_time.tzinfo != local.anchor_time.tzinfo
    assert utc.anchor_time == local.anchor_time
    assert utc.scope_hash == local.scope_hash


@pytest.mark.parametrize(
    "referenced_task_ids",
    [(), ("task-1", "task-2"), ("task-other",)],
)
def test_follow_up_requires_one_matching_trusted_task_reference(
    referenced_task_ids: tuple[str, ...],
) -> None:
    patch = validated_patch(dialog_act="follow_up")
    with pytest.raises(IntentReductionError, match="INTENT_REFERENCE_AMBIGUOUS"):
        IntentStateReducer().apply(
            previous_frame(),
            patch,
            message(referenced_task_ids=referenced_task_ids),
        )


def test_follow_up_with_unique_matching_task_reference_is_applied() -> None:
    result = IntentStateReducer().apply(
        previous_frame(),
        validated_patch(dialog_act="follow_up"),
        message(referenced_task_ids=("task-1",)),
    )
    assert result.revision == 2
    assert result.dialog_act == "follow_up"


def test_remove_from_absent_collections_is_semantic_noop() -> None:
    payload = previous_frame().model_dump(exclude={"scope_hash"})
    payload["exclusions"] = None
    payload["source_constraints"] = None
    old = IntentFrameV2.model_validate(payload)
    patch = validated_patch(
        explicit_operation("exclusions", ["不存在"], operation="remove"),
        explicit_operation("event_regions", ["US"], operation="remove"),
    )
    result = IntentStateReducer().apply(old, patch, message())
    assert result.exclusions is None
    assert result.source_constraints is None
    assert result.scope_hash == old.scope_hash


def test_remove_missing_output_item_preserves_existing_wrapper() -> None:
    old = previous_frame()
    patch = validated_patch(
        explicit_operation("target_platforms", ["douyin"], operation="remove")
    )
    result = IntentStateReducer().apply(old, patch, message())
    assert result.output_requirements == old.output_requirements
    assert result.scope_hash == old.scope_hash


def test_inherited_temporal_update_preserves_original_anchor() -> None:
    old_payload = previous_frame().model_dump(exclude={"scope_hash"})
    old_payload["temporal"] = {
        "value": {
            "kind": "calendar_period",
            "text": "昨天",
            "period": "day",
            "offset": -1,
        },
        "origin": "inherited",
        "inherited_revision": 0,
    }
    old = IntentFrameV2.model_validate(old_payload)
    patch = IntentPatchValidator().validate(
        {
            "base_revision": 1,
            "dialog_act": "refine",
            "field_operations": [
                {
                    "operation": "set",
                    "field_name": "temporal",
                    "value": {
                        "value": {
                            "kind": "calendar_period",
                            "text": "昨天",
                            "period": "day",
                            "offset": -1,
                        },
                        "origin": "inherited",
                        "inherited_revision": 1,
                    },
                }
            ],
        },
        {"m-2": "继续"},
        TrustedIntentScope(
            task_id="task-1",
            current_message_id="m-2",
            user_message_ids=frozenset({"m-2"}),
            visible_revisions=frozenset({0, 1}),
        ),
    )
    assert patch.is_valid
    result = IntentStateReducer().apply(
        old,
        patch,
        message(
            text="继续",
            received_at="2026-09-16T09:41:00-04:00",
            timezone="America/New_York",
        ),
    )
    assert result.temporal is not None
    assert result.temporal.origin == "inherited"
    assert result.anchor_time == old.anchor_time
    assert result.timezone == old.timezone


def test_unresolved_references_are_preserved_for_decision_policy() -> None:
    patch = IntentPatchValidator().validate(
        {
            "base_revision": 1,
            "dialog_act": "follow_up",
            "unresolved_references": ["继续的是哪个任务"],
        },
        {"m-2": "继续"},
        TrustedIntentScope(
            task_id="task-1",
            current_message_id="m-2",
            user_message_ids=frozenset({"m-2"}),
            visible_revisions=frozenset({1}),
        ),
    )
    assert patch.is_valid
    result = IntentStateReducer().apply(
        previous_frame(),
        patch,
        message(text="继续", referenced_task_ids=("task-1",)),
    )
    assert result.unresolved_references == ("继续的是哪个任务",)


@pytest.mark.parametrize("previous", [None, "old-task"])
def test_new_task_rejects_inherited_business_fields(
    previous: str | None,
) -> None:
    patch = IntentPatchValidator().validate(
        {
            "base_revision": 0,
            "dialog_act": "new_task",
            "field_operations": [
                {
                    "operation": "set",
                    "field_name": "topic",
                    "value": {
                        "value": "旧任务主题",
                        "origin": "inherited",
                        "inherited_revision": 0,
                    },
                }
            ],
        },
        {"m-new": "继续旧主题"},
        TrustedIntentScope(
            task_id="task-new",
            current_message_id="m-new",
            user_message_ids=frozenset({"m-new"}),
            visible_revisions=frozenset({0}),
        ),
    )
    assert patch.is_valid
    old = previous_frame() if previous is not None else None
    with pytest.raises(IntentReductionError, match="INTENT_CROSS_TASK_INHERITANCE"):
        IntentStateReducer().apply(
            old,
            patch,
            message(
                task_id="task-new",
                message_id="m-new",
                text="继续旧主题",
            ),
        )


@pytest.mark.parametrize("default_first", [False, True])
def test_output_leaf_provenance_allows_default_for_unset_style(
    default_first: bool,
) -> None:
    remove_platform = explicit_operation(
        "target_platforms", ["wechat"], operation="remove"
    )
    default_style = default_operation("output_style", "简洁")
    operations = (
        (default_style, remove_platform)
        if default_first
        else (remove_platform, default_style)
    )
    result = IntentStateReducer().apply(
        previous_frame(),
        validated_default_patch(*operations),
        message(),
    )
    assert result.output_requirements is not None
    assert result.output_requirements.value is not None
    assert result.output_requirements.value.target_platforms == ("xiaohongshu",)
    assert result.output_requirements.value.style == "简洁"
    provenance = {item.field_name: item.origin for item in result.leaf_provenance}
    assert provenance["target_platforms"] == "explicit"
    assert provenance["output_style"] == "default"


@pytest.mark.parametrize("default_first", [False, True])
def test_source_leaf_provenance_is_independent_per_field(
    default_first: bool,
) -> None:
    explicit_region = explicit_operation(
        "event_regions", ["CN"], operation="append"
    )
    default_language = default_operation(
        "source_languages", ["zh"], operation="append"
    )
    operations = (
        (default_language, explicit_region)
        if default_first
        else (explicit_region, default_language)
    )
    result = IntentStateReducer().apply(
        previous_frame(),
        validated_default_patch(*operations),
        message(),
    )
    assert result.source_constraints is not None
    assert result.source_constraints.value is not None
    assert result.source_constraints.value.event_regions == ("CN",)
    assert result.source_constraints.value.languages == ("zh",)
    provenance = {item.field_name: item.origin for item in result.leaf_provenance}
    assert provenance["event_regions"] == "explicit"
    assert provenance["source_languages"] == "default"


def test_leaf_provenance_survives_roundtrip_and_next_revision() -> None:
    first = IntentStateReducer().apply(
        previous_frame(),
        validated_default_patch(
            explicit_operation(
                "event_regions", ["CN"], operation="append"
            ),
            default_operation(
                "source_languages", ["zh"], operation="append"
            ),
        ),
        message(),
    )
    restored = IntentFrameV2.model_validate(first.model_dump())
    second = IntentStateReducer().apply(
        restored,
        validated_default_patch(
            default_operation("event_regions", ["US"], operation="append"),
            base_revision=2,
            message_id="m-3",
        ),
        message(message_id="m-3"),
    )
    assert second.source_constraints is not None
    assert second.source_constraints.value is not None
    assert second.source_constraints.value.event_regions == ("CN",)
    assert second.source_constraints.value.languages == ("zh",)


def test_complete_leaf_provenance_does_not_recreate_aggregate_origin() -> None:
    first = IntentStateReducer().apply(
        previous_frame(),
        validated_patch(
            explicit_operation(
                "target_platforms", ["wechat"], operation="remove"
            )
        ),
        message(),
    )
    restored = IntentFrameV2.model_validate(first.model_dump())
    second = IntentStateReducer().apply(
        restored,
        validated_default_patch(
            default_operation("output_style", "简洁"),
            base_revision=2,
            message_id="m-3",
        ),
        message(message_id="m-3"),
    )
    assert second.output_requirements is not None
    assert second.output_requirements.value is not None
    assert second.output_requirements.value.target_platforms == ("xiaohongshu",)
    assert second.output_requirements.value.style == "简洁"


def test_complete_leaf_provenance_rejects_missing_required_entries() -> None:
    payload = previous_frame().model_dump(exclude={"scope_hash"})
    payload["leaf_provenance"] = []
    payload["leaf_provenance_complete"] = True
    with pytest.raises(ValueError, match="LEAF_PROVENANCE_INCOMPLETE"):
        IntentFrameV2.model_validate(payload)


def test_reducer_defends_against_unvalidated_incomplete_provenance() -> None:
    old = previous_frame().model_copy(
        update={"leaf_provenance": (), "leaf_provenance_complete": True}
    )
    result = IntentStateReducer().apply(
        old,
        validated_default_patch(
            default_operation("output_language", "en-US")
        ),
        message(),
    )
    assert result.output_requirements is not None
    assert result.output_requirements.value is not None
    assert result.output_requirements.value.language == "zh-CN"


def test_legacy_provenance_mode_rejects_partial_leaf_map() -> None:
    payload = previous_frame().model_dump(exclude={"scope_hash"})
    payload["leaf_provenance_complete"] = False
    payload["leaf_provenance"] = [
        {
            "field_name": "output_language",
            "origin": "default",
            "default_policy_id": "attack/1",
        }
    ]
    with pytest.raises(ValueError, match="LEAF_PROVENANCE_PARTIAL_LEGACY"):
        IntentFrameV2.model_validate(payload)
