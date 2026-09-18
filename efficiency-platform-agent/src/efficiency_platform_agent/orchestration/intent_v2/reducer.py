"""Intent V2 不可变快照的确定性合并器。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, cast

from pydantic import ValidationError

from efficiency_platform_agent.contracts.intent_v2 import (
    EntityV2,
    FieldOperation,
    FieldPayload,
    FieldValue,
    GoalNodeV2,
    IntentFrameV2,
    LeafFieldProvenanceV2,
    OutputRequirementsV2,
    SourceConstraintsV2,
    SourceSpan,
    TrustedMessageV2,
    ValidatedIntentPatchV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import TemporalExpression

_ORIGIN_PRIORITY = {
    "derived": 0,
    "default": 1,
    "inherited": 2,
    "explicit": 3,
}
_SOURCE_COLLECTION_FIELDS = {
    "source_allowed_ids": "allowed_source_ids",
    "source_excluded_ids": "excluded_source_ids",
    "source_languages": "languages",
    "event_regions": "event_regions",
    "publisher_regions": "publisher_regions",
}
_OUTPUT_COLLECTION_FIELDS = {
    "output_types": "output_types",
    "target_platforms": "target_platforms",
}
_SOURCE_SCALAR_FIELDS = {"source_primary_only": "primary_only"}
_OUTPUT_SCALAR_FIELDS = {
    "output_language": "language",
    "output_style": "style",
    "citations_required": "citations_required",
}
_SOURCE_MODEL_TO_LEAF = {
    **{value: key for key, value in _SOURCE_COLLECTION_FIELDS.items()},
    **{value: key for key, value in _SOURCE_SCALAR_FIELDS.items()},
}
_OUTPUT_MODEL_TO_LEAF = {
    **{value: key for key, value in _OUTPUT_COLLECTION_FIELDS.items()},
    **{value: key for key, value in _OUTPUT_SCALAR_FIELDS.items()},
}


class IntentReductionError(ValueError):
    """Reducer 的稳定、可被 Pipeline 映射的失败。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class IntentStateReducer:
    """不访问时钟、模型、工具或仓储的 IntentFrame 纯合并器。"""

    def apply(
        self,
        previous: IntentFrameV2 | None,
        patch: ValidatedIntentPatchV2,
        trusted_message: TrustedMessageV2,
    ) -> IntentFrameV2:
        if patch.patch is None:
            raise IntentReductionError(patch.error_code or "INTENT_SCHEMA_INVALID")
        parsed = patch.patch
        is_new_task = parsed.dialog_act == "new_task"
        initial_chat = parsed.dialog_act == "chat" and previous is None
        if initial_chat and (
            parsed.goal_updates or parsed.field_operations or parsed.base_revision
        ):
            raise IntentReductionError("INTENT_CHAT_STATE_INVALID")
        starts_state = is_new_task or initial_chat

        if (
            not is_new_task
            and previous is not None
            and previous.task_id != trusted_message.task_id
        ):
            raise IntentReductionError("INTENT_TASK_MISMATCH")
        if (
            patch.trusted_task_id != trusted_message.task_id
            or patch.current_message_id != trusted_message.message_id
            or trusted_message.message_id not in patch.visible_user_message_ids
        ):
            raise IntentReductionError("INTENT_PATCH_CONTEXT_MISMATCH")
        if parsed.dialog_act in {"follow_up", "resume"} and (
            trusted_message.referenced_task_ids != (trusted_message.task_id,)
        ):
            raise IntentReductionError("INTENT_REFERENCE_AMBIGUOUS")
        if (
            previous is not None
            and previous.task_id == trusted_message.task_id
            and previous.message_id == trusted_message.message_id
        ):
            return previous

        if is_new_task:
            if parsed.base_revision != 0:
                raise IntentReductionError("INTENT_REVISION_CONFLICT")
            if previous is not None and previous.task_id == trusted_message.task_id:
                raise IntentReductionError("INTENT_TASK_REUSE")
            if any(
                operation.value is not None and operation.value.origin == "inherited"
                for operation in parsed.field_operations
            ):
                raise IntentReductionError("INTENT_CROSS_TASK_INHERITANCE")
        elif not initial_chat:
            if previous is None or parsed.base_revision != previous.revision:
                raise IntentReductionError("INTENT_REVISION_CONFLICT")

        state = (
            _MutableIntentState.empty()
            if starts_state
            else _MutableIntentState.from_frame(cast(IntentFrameV2, previous))
        )
        temporal_changed = False
        for operation in parsed.field_operations:
            if operation.field_name == "temporal" and self._apply_operation(
                state, operation
            ):
                temporal_changed = True
            elif operation.field_name != "temporal":
                self._apply_operation(state, operation)

        goals = _merge_goals(
            () if starts_state else cast(IntentFrameV2, previous).goal_nodes,
            parsed.goal_updates,
        )
        revision = 1 if starts_state else cast(IntentFrameV2, previous).revision + 1
        anchor = (
            trusted_message.received_at
            if starts_state or temporal_changed
            else cast(IntentFrameV2, previous).anchor_time
        )
        timezone = (
            trusted_message.timezone
            if starts_state or temporal_changed
            else cast(IntentFrameV2, previous).timezone
        )
        ambiguities = () if starts_state else cast(IntentFrameV2, previous).ambiguities

        try:
            return IntentFrameV2(
                task_id=trusted_message.task_id,
                revision=revision,
                message_id=trusted_message.message_id,
                anchor_time=anchor,
                timezone=timezone,
                dialog_act=parsed.dialog_act,
                goal_nodes=goals,
                topic=state.topic,
                entities=state.entities,
                exclusions=state.exclusions,
                temporal=state.temporal,
                source_constraints=state.finish_source_constraints(),
                output_requirements=state.finish_output_requirements(),
                ambiguities=ambiguities,
                unresolved_references=parsed.unresolved_references,
                leaf_provenance=state.finish_leaf_provenance(),
                leaf_provenance_complete=True,
            )
        except ValidationError as exc:
            raise IntentReductionError("INTENT_STATE_INVALID") from exc

    def _apply_operation(
        self, state: _MutableIntentState, operation: FieldOperation
    ) -> bool:
        field_name = operation.field_name
        if field_name in {"topic", "temporal"}:
            changed = state.apply_atomic(field_name, operation)
            if field_name != "temporal" or not changed:
                return False
            return operation.operation == "clear" or (
                operation.value is not None and operation.value.origin != "inherited"
            )
        if field_name in {"entities", "exclusions"}:
            state.apply_collection(field_name, operation)
            return False
        if field_name == "source_constraints":
            state.apply_source_aggregate(operation)
            return False
        if field_name == "output_requirements":
            state.apply_output_aggregate(operation)
            return False
        if (
            field_name in _SOURCE_COLLECTION_FIELDS
            or field_name == "source_primary_only"
        ):
            state.apply_source_leaf(operation)
            return False
        state.apply_output_leaf(operation)
        return False


class _MutableIntentState:
    def __init__(
        self,
        *,
        topic: FieldValue[str] | None,
        entities: FieldValue[tuple[EntityV2, ...]] | None,
        exclusions: FieldValue[tuple[str, ...]] | None,
        temporal: FieldValue[TemporalExpression] | None,
        source_constraints: FieldValue[SourceConstraintsV2] | None,
        output_requirements: FieldValue[OutputRequirementsV2] | None,
        leaf_provenance: tuple[LeafFieldProvenanceV2, ...],
        leaf_provenance_complete: bool,
    ) -> None:
        self.topic = topic
        self.entities = entities
        self.exclusions = exclusions
        self.temporal = temporal
        self._source_provenance = _provenance(source_constraints)
        self._source_data = _model_data(source_constraints)
        self._output_provenance = _provenance(output_requirements)
        self._output_data = _model_data(output_requirements)
        self._leaf_provenance: dict[str, _Provenance] = {
            item.field_name: _Provenance.from_leaf(item) for item in leaf_provenance
        }
        if not leaf_provenance_complete:
            self._derive_missing_leaf_provenance(
                source_constraints, output_requirements
            )
        self._ensure_required_leaf_provenance(source_constraints, output_requirements)

    @classmethod
    def empty(cls) -> _MutableIntentState:
        return cls(
            topic=None,
            entities=None,
            exclusions=None,
            temporal=None,
            source_constraints=None,
            output_requirements=None,
            leaf_provenance=(),
            leaf_provenance_complete=True,
        )

    @classmethod
    def from_frame(cls, frame: IntentFrameV2) -> _MutableIntentState:
        return cls(
            topic=frame.topic,
            entities=frame.entities,
            exclusions=frame.exclusions,
            temporal=frame.temporal,
            source_constraints=frame.source_constraints,
            output_requirements=frame.output_requirements,
            leaf_provenance=frame.leaf_provenance,
            leaf_provenance_complete=frame.leaf_provenance_complete,
        )

    def apply_atomic(self, field_name: str, operation: FieldOperation) -> bool:
        existing = self.topic if field_name == "topic" else self.temporal
        if operation.operation == "clear":
            changed = existing is not None
            if field_name == "topic":
                self.topic = None
            else:
                self.temporal = None
            return changed
        incoming = _required_value(operation)
        if not _can_replace(existing.origin if existing else None, incoming.origin):
            return False
        if field_name == "topic":
            self.topic = _copy_value(incoming, cast(str, incoming.value))
        else:
            self.temporal = _copy_value(
                incoming, cast(TemporalExpression, incoming.value)
            )
        return True

    def apply_collection(self, field_name: str, operation: FieldOperation) -> None:
        existing = self.entities if field_name == "entities" else self.exclusions
        incoming = _required_value(operation)
        if not _can_replace(existing.origin if existing else None, incoming.origin):
            return
        old_values = (
            () if existing is None or existing.value is None else existing.value
        )
        new_values = cast(tuple[object, ...], incoming.value)
        merged, changed = _update_collection(
            old_values, new_values, operation.operation
        )
        if not changed:
            return
        if field_name == "entities":
            self.entities = _copy_value(incoming, cast(tuple[EntityV2, ...], merged))
        else:
            self.exclusions = _copy_value(incoming, cast(tuple[str, ...], merged))

    def apply_source_aggregate(self, operation: FieldOperation) -> None:
        if operation.operation == "clear":
            self._source_provenance = None
            self._source_data = None
            self._drop_leaf_provenance(_SOURCE_MODEL_TO_LEAF.values())
            return
        incoming = _required_value(operation)
        if not self._can_replace_aggregate(
            _SOURCE_MODEL_TO_LEAF.values(), self._source_provenance, incoming.origin
        ):
            return
        source = cast(SourceConstraintsV2, incoming.value)
        provenance = _provenance(incoming)
        assert provenance is not None
        self._source_provenance = provenance
        self._source_data = source.model_dump(mode="python")
        self._replace_aggregate_leaf_provenance(
            _SOURCE_MODEL_TO_LEAF, source.model_fields_set, provenance
        )

    def apply_output_aggregate(self, operation: FieldOperation) -> None:
        if operation.operation == "clear":
            self._output_provenance = None
            self._output_data = None
            self._drop_leaf_provenance(_OUTPUT_MODEL_TO_LEAF.values())
            return
        incoming = _required_value(operation)
        if not self._can_replace_aggregate(
            _OUTPUT_MODEL_TO_LEAF.values(), self._output_provenance, incoming.origin
        ):
            return
        output = cast(OutputRequirementsV2, incoming.value)
        provenance = _provenance(incoming)
        assert provenance is not None
        self._output_provenance = provenance
        self._output_data = output.model_dump(mode="python")
        self._replace_aggregate_leaf_provenance(
            _OUTPUT_MODEL_TO_LEAF, output.model_fields_set, provenance
        )

    def apply_source_leaf(self, operation: FieldOperation) -> None:
        if operation.operation == "clear":
            assert operation.source_span is not None
            if self._source_data is None:
                return
            self._source_data = dict(self._source_data or {})
            self._source_data["primary_only"] = False
            provenance = _Provenance.explicit(operation.source_span)
            self._source_provenance = provenance
            self._leaf_provenance[operation.field_name] = provenance
            return
        incoming = _required_value(operation)
        existing = self._leaf_provenance.get(operation.field_name)
        if not _can_replace(existing.origin if existing else None, incoming.origin):
            return
        if operation.field_name == "source_primary_only":
            self._source_data = dict(self._source_data or {})
            self._source_data["primary_only"] = cast(bool, incoming.value)
        else:
            key = _SOURCE_COLLECTION_FIELDS[operation.field_name]
            source_data = self._source_data or {}
            current = cast(tuple[object, ...], source_data.get(key) or ())
            values = cast(tuple[object, ...], incoming.value)
            updated, changed = _update_collection(current, values, operation.operation)
            if not changed:
                return
            self._source_data = dict(source_data)
            self._source_data[key] = updated
        incoming_provenance = _provenance(incoming)
        assert incoming_provenance is not None
        self._source_provenance = incoming_provenance
        self._leaf_provenance[operation.field_name] = incoming_provenance

    def apply_output_leaf(self, operation: FieldOperation) -> None:
        if operation.operation == "clear":
            assert operation.source_span is not None
            if self._output_data is None:
                return
            self._output_data = dict(self._output_data or {})
            if operation.field_name == "output_style":
                self._output_data["style"] = None
            elif operation.field_name == "citations_required":
                self._output_data["citations_required"] = True
            else:
                raise IntentReductionError("INTENT_CLEAR_REQUIRED_FIELD")
            provenance = _Provenance.explicit(operation.source_span)
            self._output_provenance = provenance
            self._leaf_provenance[operation.field_name] = provenance
            return
        incoming = _required_value(operation)
        existing = self._leaf_provenance.get(operation.field_name)
        if not _can_replace(existing.origin if existing else None, incoming.origin):
            return
        if operation.field_name in _OUTPUT_COLLECTION_FIELDS:
            key = _OUTPUT_COLLECTION_FIELDS[operation.field_name]
            output_data = self._output_data or {}
            current = cast(tuple[object, ...], output_data.get(key) or ())
            values = cast(tuple[object, ...], incoming.value)
            updated, changed = _update_collection(current, values, operation.operation)
            if not changed:
                return
            self._output_data = dict(output_data)
            self._output_data[key] = updated
        else:
            self._output_data = dict(self._output_data or {})
            key = _OUTPUT_SCALAR_FIELDS[operation.field_name]
            self._output_data[key] = incoming.value
        incoming_provenance = _provenance(incoming)
        assert incoming_provenance is not None
        self._output_provenance = incoming_provenance
        self._leaf_provenance[operation.field_name] = incoming_provenance

    def finish_source_constraints(self) -> FieldValue[SourceConstraintsV2] | None:
        if self._source_data is None:
            return None
        try:
            value = SourceConstraintsV2.model_validate(self._source_data)
        except ValidationError as exc:
            raise IntentReductionError("INTENT_STATE_INVALID") from exc
        assert self._source_provenance is not None
        return self._source_provenance.wrap(value)

    def finish_output_requirements(self) -> FieldValue[OutputRequirementsV2] | None:
        if self._output_data is None:
            return None
        try:
            value = OutputRequirementsV2.model_validate(self._output_data)
        except ValidationError as exc:
            raise IntentReductionError("INTENT_STATE_INVALID") from exc
        assert self._output_provenance is not None
        return self._output_provenance.wrap(value)

    def finish_leaf_provenance(self) -> tuple[LeafFieldProvenanceV2, ...]:
        return tuple(
            provenance.to_leaf(field_name)
            for field_name, provenance in sorted(self._leaf_provenance.items())
        )

    def _derive_missing_leaf_provenance(
        self,
        source: FieldValue[SourceConstraintsV2] | None,
        output: FieldValue[OutputRequirementsV2] | None,
    ) -> None:
        self._derive_wrapper_leaf_provenance(source, _SOURCE_MODEL_TO_LEAF)
        self._derive_wrapper_leaf_provenance(output, _OUTPUT_MODEL_TO_LEAF)

    def _derive_wrapper_leaf_provenance[T](
        self,
        wrapper: FieldValue[T] | None,
        mapping: dict[str, str],
    ) -> None:
        provenance = _provenance(wrapper)
        if wrapper is None or wrapper.value is None or provenance is None:
            return
        model = cast(SourceConstraintsV2 | OutputRequirementsV2, wrapper.value)
        for model_name in model.model_fields_set:
            leaf_name = mapping.get(model_name)
            if leaf_name is not None:
                self._leaf_provenance.setdefault(leaf_name, provenance)

    def _ensure_required_leaf_provenance(
        self,
        source: FieldValue[SourceConstraintsV2] | None,
        output: FieldValue[OutputRequirementsV2] | None,
    ) -> None:
        if source is not None and source.value is not None:
            required_source: set[str] = set()
            if source.value.allowed_source_ids is not None:
                required_source.add("allowed_source_ids")
            if source.value.excluded_source_ids:
                required_source.add("excluded_source_ids")
            if source.value.languages is not None:
                required_source.add("languages")
            if source.value.event_regions is not None:
                required_source.add("event_regions")
            if source.value.publisher_regions is not None:
                required_source.add("publisher_regions")
            if source.value.primary_only:
                required_source.add("primary_only")
            self._derive_required_model_fields(
                source, _SOURCE_MODEL_TO_LEAF, required_source
            )
        if output is not None and output.value is not None:
            required_output = {"output_types", "language"}
            if output.value.target_platforms is not None:
                required_output.add("target_platforms")
            if output.value.style is not None:
                required_output.add("style")
            if not output.value.citations_required:
                required_output.add("citations_required")
            self._derive_required_model_fields(
                output, _OUTPUT_MODEL_TO_LEAF, required_output
            )

    def _derive_required_model_fields[T](
        self,
        wrapper: FieldValue[T],
        mapping: dict[str, str],
        required_model_fields: set[str],
    ) -> None:
        provenance = _provenance(wrapper)
        assert provenance is not None
        for model_name in required_model_fields:
            leaf_name = mapping[model_name]
            self._leaf_provenance.setdefault(leaf_name, provenance)

    def _replace_aggregate_leaf_provenance(
        self,
        mapping: dict[str, str],
        model_fields_set: set[str],
        provenance: _Provenance,
    ) -> None:
        self._drop_leaf_provenance(mapping.values())
        for model_name in model_fields_set:
            leaf_name = mapping.get(model_name)
            if leaf_name is not None:
                self._leaf_provenance[leaf_name] = provenance

    def _drop_leaf_provenance(self, field_names: Iterable[str]) -> None:
        for field_name in field_names:
            self._leaf_provenance.pop(field_name, None)

    def _can_replace_aggregate(
        self,
        field_names: Iterable[str],
        fallback: _Provenance | None,
        incoming_origin: str,
    ) -> bool:
        origins = [
            self._leaf_provenance[field_name].origin
            for field_name in field_names
            if field_name in self._leaf_provenance
        ]
        if not origins and fallback is not None:
            origins.append(fallback.origin)
        return all(_can_replace(origin, incoming_origin) for origin in origins)


def _required_value(operation: FieldOperation) -> FieldValue[FieldPayload]:
    if operation.value is None:
        raise IntentReductionError("INTENT_SCHEMA_INVALID")
    return operation.value


def _can_replace(existing_origin: str | None, incoming_origin: str) -> bool:
    if existing_origin is None:
        return True
    return _ORIGIN_PRIORITY[incoming_origin] >= _ORIGIN_PRIORITY[existing_origin]


def _copy_value[S, T](template: FieldValue[S], value: T) -> FieldValue[T]:
    return FieldValue[T](
        value=value,
        origin=template.origin,
        source_span=template.source_span,
        inherited_revision=template.inherited_revision,
        normalizer_version=template.normalizer_version,
        default_policy_id=template.default_policy_id,
        validation=template.validation,
        reason_code=template.reason_code,
    )


def _model_data[T](value: FieldValue[T] | None) -> dict[str, object] | None:
    if value is None or value.value is None:
        return None
    model = cast(SourceConstraintsV2 | OutputRequirementsV2, value.value)
    return model.model_dump(mode="python")


@dataclass(frozen=True, slots=True)
class _Provenance:
    origin: Literal["explicit", "inherited", "default", "derived"]
    source_span: SourceSpan | None
    inherited_revision: int | None
    normalizer_version: str | None
    default_policy_id: str | None
    validation: Literal["valid", "ambiguous", "invalid", "unknown"]
    reason_code: str | None

    @classmethod
    def explicit(cls, source_span: SourceSpan) -> _Provenance:
        return cls("explicit", source_span, None, None, None, "valid", None)

    @classmethod
    def from_leaf(cls, value: LeafFieldProvenanceV2) -> _Provenance:
        return cls(
            value.origin,
            value.source_span,
            value.inherited_revision,
            value.normalizer_version,
            value.default_policy_id,
            "valid",
            None,
        )

    def wrap[T](self, value: T) -> FieldValue[T]:
        return FieldValue[T](
            value=value,
            origin=self.origin,
            source_span=self.source_span,
            inherited_revision=self.inherited_revision,
            normalizer_version=self.normalizer_version,
            default_policy_id=self.default_policy_id,
            validation=self.validation,
            reason_code=self.reason_code,
        )

    def to_leaf(self, field_name: str) -> LeafFieldProvenanceV2:
        return LeafFieldProvenanceV2(
            field_name=field_name,  # type: ignore[arg-type]
            origin=self.origin,
            source_span=self.source_span,
            inherited_revision=self.inherited_revision,
            normalizer_version=self.normalizer_version,
            default_policy_id=self.default_policy_id,
        )


def _provenance[T](value: FieldValue[T] | None) -> _Provenance | None:
    if value is None:
        return None
    return _Provenance(
        value.origin,
        value.source_span,
        value.inherited_revision,
        value.normalizer_version,
        value.default_policy_id,
        value.validation,
        value.reason_code,
    )


def _update_collection(
    current: Iterable[object], incoming: Iterable[object], operation: str
) -> tuple[tuple[object, ...], bool]:
    values = list(current)
    original = tuple(values)
    if operation == "append":
        for item in incoming:
            if item not in values:
                values.append(item)
    elif operation == "remove":
        removals = list(incoming)
        values = [item for item in values if item not in removals]
    else:
        raise IntentReductionError("INTENT_SCHEMA_INVALID")
    updated = tuple(values)
    return updated, updated != original


def _merge_goals(
    existing: tuple[GoalNodeV2, ...], updates: tuple[GoalNodeV2, ...]
) -> tuple[GoalNodeV2, ...]:
    positions = {goal.goal_id: index for index, goal in enumerate(existing)}
    merged = list(existing)
    for goal in updates:
        index = positions.get(goal.goal_id)
        if index is None:
            positions[goal.goal_id] = len(merged)
            merged.append(goal)
        else:
            merged[index] = goal
    return tuple(merged)


__all__ = ["IntentReductionError", "IntentStateReducer"]
