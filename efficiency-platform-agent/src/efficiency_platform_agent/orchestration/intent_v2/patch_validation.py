"""IntentPatchV2 的字段操作、来源引用和可信边界校验。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import ValidationError

from efficiency_platform_agent.contracts.intent_v2 import (
    EntityV2,
    FieldOperation,
    FieldPayload,
    FieldValue,
    IntentPatchV2,
    OutputRequirementsV2,
    SourceConstraintsV2,
    SourceSpan,
)
from efficiency_platform_agent.contracts.temporal_v2 import (
    BeforeAfterExpression,
    CalendarPeriodExpression,
    ExplicitRangeExpression,
    RollingDurationExpression,
    UnspecifiedTemporalExpression,
)

_SCALAR_FIELDS = frozenset(
    {
        "topic",
        "temporal",
        "source_constraints",
        "output_requirements",
        "source_primary_only",
        "output_language",
        "output_style",
        "citations_required",
    }
)
_COLLECTION_FIELDS = frozenset(
    {
        "entities",
        "exclusions",
        "source_allowed_ids",
        "source_excluded_ids",
        "source_languages",
        "event_regions",
        "publisher_regions",
        "output_types",
        "target_platforms",
    }
)
_TEMPORAL_TYPES = (
    BeforeAfterExpression,
    CalendarPeriodExpression,
    ExplicitRangeExpression,
    RollingDurationExpression,
    UnspecifiedTemporalExpression,
)
_SCALAR_TEXT_LIMITS = {
    "topic": 4_000,
    "output_language": 32,
    "output_style": 256,
}
_COLLECTION_LIMITS = {
    "entities": 64,
    "exclusions": 64,
    "source_allowed_ids": 64,
    "source_excluded_ids": 64,
    "source_languages": 16,
    "event_regions": 32,
    "publisher_regions": 32,
    "output_types": 16,
    "target_platforms": 16,
}
_COLLECTION_ITEM_LIMITS = {
    "exclusions": 512,
    "source_allowed_ids": 128,
    "source_excluded_ids": 128,
    "source_languages": 128,
    "event_regions": 128,
    "publisher_regions": 128,
    "output_types": 128,
    "target_platforms": 128,
}
_ERROR_CODE = "INTENT_SCHEMA_INVALID"


@dataclass(frozen=True, slots=True)
class TrustedIntentScope:
    """只由服务端建立的任务与来源校验范围。"""

    task_id: str
    current_message_id: str
    user_message_ids: frozenset[str]
    visible_revisions: frozenset[int]
    allowed_default_policy_ids: frozenset[str] = frozenset()
    allowed_normalizer_versions: frozenset[str] = frozenset()
    allowed_intent_parameter_names: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise ValueError("task_id 必须是非空字符串")
        if (
            not isinstance(self.current_message_id, str)
            or not self.current_message_id.strip()
            or len(self.current_message_id) > 128
        ):
            raise ValueError("current_message_id 必须是有界非空字符串")
        for name in (
            "user_message_ids",
            "allowed_default_policy_ids",
            "allowed_normalizer_versions",
            "allowed_intent_parameter_names",
        ):
            values = getattr(self, name)
            if not isinstance(values, frozenset) or any(
                not isinstance(value, str) or not value.strip() or len(value) > 128
                for value in values
            ):
                raise ValueError(f"{name} 必须是有界非空字符串集合")
        if not isinstance(self.visible_revisions, frozenset) or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in self.visible_revisions
        ):
            raise ValueError("visible_revisions 必须是非负整数集合")


@dataclass(frozen=True, slots=True)
class ValidatedIntentPatch:
    """Patch 校验结果；成功值与稳定错误互斥。"""

    patch: IntentPatchV2 | None
    error_code: str | None = None
    reason_code: str | None = None
    trusted_task_id: str | None = None
    current_message_id: str | None = None
    visible_user_message_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if (self.patch is None) == (self.error_code is None):
            raise ValueError("patch 与 error_code 必须且只能提供一个")
        if self.error_code is not None and self.error_code != _ERROR_CODE:
            raise ValueError("error_code 非法")
        if self.patch is not None and self.reason_code is not None:
            raise ValueError("成功结果不能携带 reason_code")
        if self.error_code is not None and (
            self.reason_code is None or not self.reason_code.strip()
        ):
            raise ValueError("失败结果必须携带 reason_code")
        if self.patch is not None and (
            self.trusted_task_id is None
            or not self.trusted_task_id.strip()
            or self.current_message_id is None
            or not self.current_message_id.strip()
            or not self.visible_user_message_ids
        ):
            raise ValueError("成功结果必须绑定可信任务和消息范围")
        if self.patch is None and (
            self.trusted_task_id is not None
            or self.current_message_id is not None
            or self.visible_user_message_ids
        ):
            raise ValueError("失败结果不能携带可信范围")

    @property
    def is_valid(self) -> bool:
        return self.patch is not None


class IntentPatchValidator:
    """不调用模型或工具的纯 Patch 校验器。"""

    def validate(
        self,
        patch: IntentPatchV2 | Mapping[str, object],
        visible_messages: Mapping[str, str],
        trusted_scope: TrustedIntentScope,
    ) -> ValidatedIntentPatch:
        if not isinstance(trusted_scope, TrustedIntentScope):
            raise TypeError("trusted_scope 类型不正确")
        messages = self._validate_messages(visible_messages)
        if (
            trusted_scope.current_message_id not in trusted_scope.user_message_ids
            or trusted_scope.current_message_id not in messages
        ):
            raise ValueError("current_message_id 不在可信可见用户消息中")
        try:
            parsed = (
                patch
                if isinstance(patch, IntentPatchV2)
                else IntentPatchV2.model_validate(patch)
            )
        except (ValidationError, TypeError, ValueError):
            return self._invalid("PATCH_SCHEMA_INVALID")
        for goal in parsed.goal_updates:
            if any(
                parameter.name not in trusted_scope.allowed_intent_parameter_names
                for parameter in goal.parameters
            ):
                return self._invalid("GOAL_PARAMETER_NOT_ALLOWED")
        for operation in parsed.field_operations:
            reason = self._validate_operation(operation, messages, trusted_scope)
            if reason is not None:
                return self._invalid(reason)
        return ValidatedIntentPatch(
            parsed,
            trusted_task_id=trusted_scope.task_id,
            current_message_id=trusted_scope.current_message_id,
            visible_user_message_ids=trusted_scope.user_message_ids,
        )

    @staticmethod
    def _validate_messages(visible_messages: Mapping[str, str]) -> dict[str, str]:
        if not isinstance(visible_messages, Mapping):
            raise TypeError("visible_messages 必须是只读映射")
        messages = dict(visible_messages)
        if any(
            not isinstance(identifier, str)
            or not identifier.strip()
            or len(identifier) > 128
            or not isinstance(text, str)
            for identifier, text in messages.items()
        ):
            raise ValueError("visible_messages 包含非法消息")
        return messages

    def _validate_operation(
        self,
        operation: FieldOperation,
        messages: Mapping[str, str],
        scope: TrustedIntentScope,
    ) -> str | None:
        if operation.operation in {"set", "clear"}:
            if operation.field_name not in _SCALAR_FIELDS:
                return "FIELD_OPERATION_NOT_ALLOWED"
        elif operation.field_name not in _COLLECTION_FIELDS:
            return "FIELD_OPERATION_NOT_ALLOWED"

        if operation.operation == "clear":
            if operation.source_span is None:
                return "CLEAR_SOURCE_REQUIRED"
            return self._validate_span(operation.source_span, messages, scope)

        if operation.source_span is not None:
            return "OPERATION_SOURCE_FORBIDDEN"
        value = operation.value
        if value is None or value.validation != "valid" or value.value is None:
            return "FIELD_VALUE_INVALID"
        if operation.operation == "set":
            if not self._scalar_value_matches(operation.field_name, value.value):
                return "FIELD_VALUE_TYPE_INVALID"
        else:
            if not self._collection_value_matches(operation.field_name, value.value):
                return "FIELD_VALUE_TYPE_INVALID"
            assert isinstance(value.value, tuple)
            if len(set(value.value)) != len(value.value):
                return "COLLECTION_VALUE_INVALID"
        return self._validate_provenance(value, messages, scope)

    @staticmethod
    def _scalar_value_matches(field_name: str, value: FieldPayload) -> bool:
        if field_name in _SCALAR_TEXT_LIMITS:
            return (
                isinstance(value, str)
                and bool(value.strip())
                and len(value) <= _SCALAR_TEXT_LIMITS[field_name]
            )
        if field_name in {"source_primary_only", "citations_required"}:
            return type(value) is bool
        if field_name == "temporal":
            return isinstance(value, _TEMPORAL_TYPES)
        if field_name == "source_constraints":
            return isinstance(value, SourceConstraintsV2)
        if field_name == "output_requirements":
            return isinstance(value, OutputRequirementsV2)
        return False

    @staticmethod
    def _collection_value_matches(field_name: str, value: FieldPayload) -> bool:
        if (
            not isinstance(value, tuple)
            or not value
            or len(value) > _COLLECTION_LIMITS[field_name]
        ):
            return False
        if field_name == "entities":
            return all(isinstance(item, EntityV2) for item in value)
        item_limit = _COLLECTION_ITEM_LIMITS[field_name]
        return all(
            isinstance(item, str) and bool(item.strip()) and len(item) <= item_limit
            for item in value
        )

    def _validate_provenance(
        self,
        value: FieldValue[FieldPayload],
        messages: Mapping[str, str],
        scope: TrustedIntentScope,
    ) -> str | None:
        if value.origin == "explicit":
            if any(
                item is not None
                for item in (
                    value.inherited_revision,
                    value.normalizer_version,
                    value.default_policy_id,
                )
            ):
                return "PROVENANCE_METADATA_CONFLICT"
            if value.source_span is None:
                return "EXPLICIT_SOURCE_REQUIRED"
            return self._validate_span(value.source_span, messages, scope)
        if value.source_span is not None:
            return "PROVENANCE_METADATA_CONFLICT"
        if value.origin == "inherited":
            if (
                value.normalizer_version is not None
                or value.default_policy_id is not None
            ):
                return "PROVENANCE_METADATA_CONFLICT"
            if value.inherited_revision not in scope.visible_revisions:
                return "INHERITED_REVISION_NOT_VISIBLE"
            return None
        if value.inherited_revision is not None:
            return "PROVENANCE_METADATA_CONFLICT"
        if value.origin == "default":
            if value.normalizer_version is not None:
                return "PROVENANCE_METADATA_CONFLICT"
            if value.default_policy_id not in scope.allowed_default_policy_ids:
                return "DEFAULT_POLICY_NOT_ALLOWED"
            return None
        if value.default_policy_id is not None:
            return "PROVENANCE_METADATA_CONFLICT"
        if value.normalizer_version not in scope.allowed_normalizer_versions:
            return "NORMALIZER_VERSION_NOT_ALLOWED"
        return None

    @staticmethod
    def _validate_span(
        span: SourceSpan,
        messages: Mapping[str, str],
        scope: TrustedIntentScope,
    ) -> str | None:
        if span.message_id not in scope.user_message_ids:
            return "SOURCE_MESSAGE_NOT_TRUSTED_USER"
        text = messages.get(span.message_id)
        if text is None:
            return "SOURCE_MESSAGE_NOT_VISIBLE"
        if not (0 <= span.start < span.end <= len(text)):
            return "SOURCE_SPAN_OUT_OF_RANGE"
        if text[span.start : span.end] != span.quoted_text:
            return "SOURCE_SPAN_MISMATCH"
        return None

    @staticmethod
    def _invalid(reason_code: str) -> ValidatedIntentPatch:
        return ValidatedIntentPatch(None, _ERROR_CODE, reason_code)


__all__ = [
    "IntentPatchValidator",
    "TrustedIntentScope",
    "ValidatedIntentPatch",
]
