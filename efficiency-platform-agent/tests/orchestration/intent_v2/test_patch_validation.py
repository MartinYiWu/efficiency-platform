"""Intent Patch 字段来源与可信边界的行为测试。"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from efficiency_platform_agent.orchestration.intent_v2.patch_validation import (
    IntentPatchValidator,
    TrustedIntentScope,
)


def scope(**changes: object) -> TrustedIntentScope:
    values: dict[str, object] = {
        "task_id": "task-1",
        "current_message_id": "m-1",
        "user_message_ids": frozenset({"m-1", "m-2"}),
        "visible_revisions": frozenset({0, 1}),
        "allowed_default_policy_ids": frozenset({"output-default/1"}),
        "allowed_normalizer_versions": frozenset({"topic-normalizer/1"}),
    }
    values.update(changes)
    return TrustedIntentScope(**values)  # type: ignore[arg-type]


def raw_patch(*operations: Mapping[str, object], **extra: object) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": "intent-patch/2",
        "base_revision": 1,
        "dialog_act": "refine",
        "goal_updates": [],
        "field_operations": list(operations),
        "unresolved_references": [],
    }
    result.update(extra)
    return result


def explicit_operation(
    *,
    field_name: str = "topic",
    value: object = "AI新闻",
    message_id: str = "m-1",
    start: int = 2,
    end: int = 6,
    quote: str = "AI新闻",
    operation: str = "set",
) -> dict[str, object]:
    return {
        "operation": operation,
        "field_name": field_name,
        "value": {
            "value": value,
            "origin": "explicit",
            "source_span": {
                "message_id": message_id,
                "start": start,
                "end": end,
                "quoted_text": quote,
            },
        },
    }


@pytest.mark.parametrize(
    ("operation", "expected_valid"),
    [
        (
            {
                "operation": "clear",
                "field_name": "topic",
                "source_span": {
                    "message_id": "m-1",
                    "start": 2,
                    "end": 6,
                    "quoted_text": "AI新闻",
                },
            },
            True,
        ),
        (explicit_operation(value=""), False),
        (
            {
                "operation": "set",
                "field_name": "topic",
                "value": {"value": None, "origin": "explicit"},
            },
            False,
        ),
    ],
)
def test_missing_clear_empty_and_set_null_are_distinct(
    operation: Mapping[str, object], expected_valid: bool
) -> None:
    validator = IntentPatchValidator()
    visible = {"m-1": "收集AI新闻"}
    result = validator.validate(raw_patch(operation), visible, scope())
    assert result.is_valid is expected_valid
    assert (result.error_code is None) is expected_valid
    assert validator.validate(raw_patch(), visible, scope()).is_valid is True


@pytest.mark.parametrize(
    ("case_id", "patch", "visible", "trusted"),
    [
        (
            "forged_span",
            raw_patch(explicit_operation(start=1, end=5, quote="AI新闻")),
            {"m-1": "收集AI新闻"},
            scope(),
        ),
        (
            "webpage_as_user_message",
            raw_patch(
                explicit_operation(
                    message_id="web-1", start=0, end=4, quote="AI新闻"
                )
            ),
            {"m-1": "收集AI新闻", "web-1": "AI新闻正文"},
            scope(),
        ),
        (
            "tenant_injection",
            raw_patch(tenant_id="tenant-attack"),
            {"m-1": "收集AI新闻"},
            scope(),
        ),
        (
            "budget_injection",
            raw_patch(budget_lease_id="lease-attack"),
            {"m-1": "收集AI新闻"},
            scope(),
        ),
    ],
)
def test_invalid_patch_cannot_cross_trusted_boundary(
    case_id: str,
    patch: Mapping[str, object],
    visible: Mapping[str, str],
    trusted: TrustedIntentScope,
) -> None:
    del case_id
    result = IntentPatchValidator().validate(patch, visible, trusted)
    assert result.is_valid is False
    assert result.patch is None
    assert result.error_code == "INTENT_SCHEMA_INVALID"


@pytest.mark.parametrize(
    ("text", "quote", "start"),
    [
        ("请看🤖AI新闻。", "🤖AI新闻", 2),
        ("AI新闻，别把第二个AI新闻漏掉", "AI新闻", 10),
        ("主题：“新能源”！", "新能源", 4),
    ],
)
def test_unicode_span_matches_original_message_exactly(
    text: str, quote: str, start: int
) -> None:
    result = IntentPatchValidator().validate(
        raw_patch(
            explicit_operation(
                value=quote,
                start=start,
                end=start + len(quote),
                quote=quote,
            )
        ),
        {"m-1": text},
        scope(),
    )
    assert result.is_valid is True
    assert result.patch is not None


@pytest.mark.parametrize(
    "operation",
    [
        explicit_operation(start=20, end=24),
        explicit_operation(start=2, end=2, quote=""),
        explicit_operation(field_name="entities", operation="set"),
        explicit_operation(field_name="topic", operation="append"),
        explicit_operation(
            field_name="exclusions", operation="append", value=()
        ),
        explicit_operation(
            field_name="exclusions",
            operation="append",
            value=tuple(f"item-{index}" for index in range(65)),
        ),
        explicit_operation(
            field_name="exclusions",
            operation="append",
            value=("x" * 513,),
        ),
    ],
)
def test_invalid_span_or_field_operation_is_rejected(
    operation: Mapping[str, object],
) -> None:
    result = IntentPatchValidator().validate(
        raw_patch(operation), {"m-1": "收集AI新闻"}, scope()
    )
    assert result.is_valid is False
    assert result.error_code == "INTENT_SCHEMA_INVALID"


@pytest.mark.parametrize(
    ("origin", "metadata", "trusted_changes", "expected"),
    [
        ("inherited", {"inherited_revision": 1}, {}, True),
        ("inherited", {"inherited_revision": 9}, {}, False),
        ("default", {"default_policy_id": "output-default/1"}, {}, True),
        ("default", {"default_policy_id": "untrusted/1"}, {}, False),
        ("derived", {"normalizer_version": "topic-normalizer/1"}, {}, True),
        ("derived", {"normalizer_version": "untrusted/1"}, {}, False),
    ],
)
def test_non_explicit_provenance_must_be_authorized(
    origin: str,
    metadata: Mapping[str, object],
    trusted_changes: Mapping[str, object],
    expected: bool,
) -> None:
    value: dict[str, object] = {"value": "AI新闻", "origin": origin}
    value.update(metadata)
    operation = {"operation": "set", "field_name": "topic", "value": value}
    result = IntentPatchValidator().validate(
        raw_patch(operation),
        {"m-1": "收集AI新闻"},
        scope(**trusted_changes),
    )
    assert result.is_valid is expected


def test_explicit_provenance_rejects_mixed_metadata() -> None:
    operation = explicit_operation()
    assert isinstance(operation["value"], dict)
    operation["value"]["default_policy_id"] = "output-default/1"
    result = IntentPatchValidator().validate(
        raw_patch(operation), {"m-1": "收集AI新闻"}, scope()
    )
    assert result.is_valid is False


def test_patch_rejects_more_than_sixty_four_operations() -> None:
    result = IntentPatchValidator().validate(
        raw_patch(*(explicit_operation() for _ in range(65))),
        {"m-1": "收集AI新闻"},
        scope(),
    )
    assert result.is_valid is False
    assert result.error_code == "INTENT_SCHEMA_INVALID"


@pytest.mark.parametrize("parameter_name", ["tenant_id", "budget_microunits"])
def test_goal_parameter_requires_server_allowlist(parameter_name: str) -> None:
    patch = raw_patch(
        goal_updates=[
            {
                "goal_id": "g-1",
                "description": "收集新闻",
                "parameters": [{"name": parameter_name, "value": "attack"}],
            }
        ]
    )
    result = IntentPatchValidator().validate(
        patch, {"m-1": "收集AI新闻"}, scope()
    )
    assert result.is_valid is False
    assert result.reason_code == "GOAL_PARAMETER_NOT_ALLOWED"


def test_goal_parameter_from_server_allowlist_is_accepted() -> None:
    patch = raw_patch(
        goal_updates=[
            {
                "goal_id": "g-1",
                "description": "挑选三条新闻",
                "parameters": [{"name": "count", "value": 3}],
            }
        ]
    )
    result = IntentPatchValidator().validate(
        patch,
        {"m-1": "收集AI新闻"},
        scope(allowed_intent_parameter_names=frozenset({"count"})),
    )
    assert result.is_valid is True


@pytest.mark.parametrize(
    ("field_name", "operation", "value"),
    [
        ("topic", "set", "AI新闻"),
        (
            "temporal",
            "set",
            {
                "kind": "calendar_period",
                "text": "昨天",
                "period": "day",
                "offset": -1,
            },
        ),
        ("source_constraints", "set", {"languages": ["zh"]}),
        (
            "output_requirements",
            "set",
            {
                "output_types": ["digest"],
                "target_platforms": ["wechat", "xiaohongshu"],
                "language": "zh-CN",
            },
        ),
        (
            "entities",
            "append",
            [{"raw_text": "OpenAI", "canonical_name": "OpenAI", "role": "topic"}],
        ),
        ("target_platforms", "remove", ["wechat"]),
    ],
)
def test_field_operations_accept_frame_compatible_typed_values(
    field_name: str, operation: str, value: object
) -> None:
    result = IntentPatchValidator().validate(
        raw_patch(
            explicit_operation(
                field_name=field_name,
                operation=operation,
                value=value,
            )
        ),
        {"m-1": "收集AI新闻"},
        scope(),
    )
    assert result.is_valid is True


@pytest.mark.parametrize(
    ("field_name", "operation", "value"),
    [
        ("topic", "set", True),
        ("temporal", "set", 42),
        ("source_constraints", "set", "anything"),
        ("output_requirements", "set", False),
        ("entities", "append", ["OpenAI"]),
        ("target_platforms", "remove", [True]),
    ],
)
def test_field_operations_reject_frame_incompatible_value_types(
    field_name: str, operation: str, value: object
) -> None:
    result = IntentPatchValidator().validate(
        raw_patch(
            explicit_operation(
                field_name=field_name,
                operation=operation,
                value=value,
            )
        ),
        {"m-1": "收集AI新闻"},
        scope(),
    )
    assert result.is_valid is False
    assert result.error_code == "INTENT_SCHEMA_INVALID"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("source_constraints", {"allowed_source_ids": ["x" * 129]}),
        ("source_constraints", {"allowed_source_ids": [""]}),
        ("source_constraints", {"primary_only": "yes"}),
        ("output_requirements", {"output_types": ["x" * 129], "language": "zh"}),
        (
            "output_requirements",
            {"output_types": ["digest"], "target_platforms": [""], "language": "zh"},
        ),
        (
            "output_requirements",
            {"output_types": ["digest"], "language": "zh", "citations_required": "no"},
        ),
        (
            "temporal",
            {
                "kind": "calendar_period",
                "text": "昨天",
                "period": "day",
                "offset": "-1",
            },
        ),
        ("entities", [{"raw_text": " ", "role": " "}]),
    ],
)
def test_nested_structured_values_keep_strict_item_boundaries(
    field_name: str, value: object
) -> None:
    operation = "append" if field_name == "entities" else "set"
    result = IntentPatchValidator().validate(
        raw_patch(
            explicit_operation(
                field_name=field_name,
                operation=operation,
                value=value,
            )
        ),
        {"m-1": "收集AI新闻"},
        scope(),
    )
    assert result.is_valid is False
    assert result.error_code == "INTENT_SCHEMA_INVALID"


@pytest.mark.parametrize(
    "patch",
    [
        {
            **raw_patch(),
            "base_revision": "1",
        },
        raw_patch(
            explicit_operation(start=False, end=True, quote="收", value="收")
        ),
        raw_patch(
            {
                "operation": "set",
                "field_name": "topic",
                "value": {
                    "value": "AI新闻",
                    "origin": "inherited",
                    "inherited_revision": True,
                },
            }
        ),
    ],
)
def test_security_relevant_integer_fields_do_not_coerce_bool_or_string(
    patch: Mapping[str, object],
) -> None:
    result = IntentPatchValidator().validate(
        patch, {"m-1": "收集AI新闻"}, scope()
    )
    assert result.is_valid is False
    assert result.reason_code == "PATCH_SCHEMA_INVALID"


def test_goal_parameter_names_must_be_unique() -> None:
    patch = raw_patch(
        goal_updates=[
            {
                "goal_id": "g-1",
                "description": "挑选新闻",
                "parameters": [
                    {"name": "count", "value": 3},
                    {"name": "count", "value": 4},
                ],
            }
        ]
    )
    result = IntentPatchValidator().validate(
        patch,
        {"m-1": "收集AI新闻"},
        scope(allowed_intent_parameter_names=frozenset({"count"})),
    )
    assert result.is_valid is False
    assert result.reason_code == "PATCH_SCHEMA_INVALID"


@pytest.mark.parametrize(
    "field_name",
    [
        "source_allowed_ids",
        "source_excluded_ids",
        "source_languages",
        "event_regions",
        "publisher_regions",
        "output_types",
        "target_platforms",
    ],
)
def test_leaf_collection_item_limits_match_frame_contract(field_name: str) -> None:
    result = IntentPatchValidator().validate(
        raw_patch(
            explicit_operation(
                field_name=field_name,
                operation="append",
                value=["x" * 129],
            )
        ),
        {"m-1": "收集AI新闻"},
        scope(),
    )
    assert result.is_valid is False
    assert result.reason_code == "FIELD_VALUE_TYPE_INVALID"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("output_language", "x" * 33),
        ("output_style", "x" * 257),
    ],
)
def test_leaf_scalar_limits_match_frame_contract(
    field_name: str, value: str
) -> None:
    result = IntentPatchValidator().validate(
        raw_patch(explicit_operation(field_name=field_name, value=value)),
        {"m-1": "收集AI新闻"},
        scope(),
    )
    assert result.is_valid is False
    assert result.reason_code == "FIELD_VALUE_TYPE_INVALID"


def test_leaf_collection_cardinality_matches_frame_contract() -> None:
    result = IntentPatchValidator().validate(
        raw_patch(
            explicit_operation(
                field_name="target_platforms",
                operation="append",
                value=[f"platform-{index}" for index in range(17)],
            )
        ),
        {"m-1": "收集AI新闻"},
        scope(),
    )
    assert result.is_valid is False
    assert result.reason_code == "FIELD_VALUE_TYPE_INVALID"
