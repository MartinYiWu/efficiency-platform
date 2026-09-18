"""语义意图 V2 的不可变中立契约。"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Literal, Protocol, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)

from efficiency_platform_agent.contracts.temporal_v2 import TemporalExpression

T = TypeVar("T")
BoundedText = Annotated[str, Field(min_length=1, max_length=4_000)]
BoundedTextCollection = Annotated[
    tuple[Annotated[str, Field(min_length=1, max_length=512)], ...],
    Field(min_length=1, max_length=64),
]
BoundedIdentifier = Annotated[str, Field(min_length=1, max_length=128)]
ScalarValue = BoundedText | StrictInt | StrictFloat | StrictBool


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceSpan(_FrozenContract):
    message_id: str = Field(min_length=1, max_length=128)
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(ge=0)
    quoted_text: str = Field(min_length=1, max_length=4_000)

    @model_validator(mode="after")
    def validate_range(self) -> SourceSpan:
        """字符区间使用 Python 的 Unicode 码点切片语义。"""

        if self.start >= self.end:
            raise ValueError("SOURCE_SPAN_INVALID")
        if self.end - self.start != len(self.quoted_text):
            raise ValueError("SOURCE_SPAN_LENGTH_MISMATCH")
        return self


class FieldValue[T](_FrozenContract):
    value: T | None
    origin: Literal["explicit", "inherited", "default", "derived"]
    source_span: SourceSpan | None = None
    inherited_revision: StrictInt | None = Field(default=None, ge=0)
    normalizer_version: str | None = Field(default=None, min_length=1, max_length=64)
    default_policy_id: str | None = Field(default=None, min_length=1, max_length=128)
    validation: Literal["valid", "ambiguous", "invalid", "unknown"] = "valid"
    reason_code: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_provenance(self) -> FieldValue[T]:
        """未知、显式、继承、默认和派生值保持不同来源语义。"""

        if self.validation == "unknown" and self.value is not None:
            raise ValueError("UNKNOWN_VALUE_MUST_BE_NULL")
        if self.validation != "unknown" and self.value is None:
            raise ValueError("KNOWN_VALUE_REQUIRED")
        if self.origin == "explicit" and self.source_span is None:
            raise ValueError("EXPLICIT_SOURCE_REQUIRED")
        if self.origin == "inherited" and self.inherited_revision is None:
            raise ValueError("INHERITED_REVISION_REQUIRED")
        if self.origin == "default" and self.default_policy_id is None:
            raise ValueError("DEFAULT_POLICY_REQUIRED")
        if self.origin == "derived" and self.normalizer_version is None:
            raise ValueError("NORMALIZER_VERSION_REQUIRED")
        return self


class EntityV2(_FrozenContract):
    raw_text: str = Field(min_length=1, max_length=512)
    canonical_name: str | None = Field(default=None, min_length=1, max_length=512)
    role: str = Field(min_length=1, max_length=128)

    @field_validator("raw_text", "canonical_name", "role")
    @classmethod
    def validate_nonblank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("ENTITY_TEXT_BLANK")
        return value


class SourceConstraintsV2(_FrozenContract):
    allowed_source_ids: tuple[BoundedIdentifier, ...] | None = Field(
        default=None, max_length=64
    )
    excluded_source_ids: tuple[BoundedIdentifier, ...] = Field(
        default=(), max_length=64
    )
    languages: tuple[BoundedIdentifier, ...] | None = Field(
        default=None, max_length=16
    )
    event_regions: tuple[BoundedIdentifier, ...] | None = Field(
        default=None, max_length=32
    )
    publisher_regions: tuple[BoundedIdentifier, ...] | None = Field(
        default=None, max_length=32
    )
    primary_only: StrictBool = False

    @field_validator(
        "allowed_source_ids",
        "excluded_source_ids",
        "languages",
        "event_regions",
        "publisher_regions",
    )
    @classmethod
    def validate_identifier_items(
        cls, value: tuple[str, ...] | None
    ) -> tuple[str, ...] | None:
        if value is not None and (
            any(not item.strip() for item in value)
            or len(set(value)) != len(value)
        ):
            raise ValueError("SOURCE_CONSTRAINT_ITEM_INVALID")
        return value


class OutputRequirementsV2(_FrozenContract):
    output_types: tuple[BoundedIdentifier, ...] = Field(min_length=1, max_length=16)
    target_platforms: tuple[BoundedIdentifier, ...] | None = Field(
        default=None, max_length=16
    )
    language: str = Field(min_length=1, max_length=32)
    style: str | None = Field(default=None, min_length=1, max_length=256)
    citations_required: StrictBool = True

    @field_validator("output_types", "target_platforms")
    @classmethod
    def validate_identifier_items(
        cls, value: tuple[str, ...] | None
    ) -> tuple[str, ...] | None:
        if value is not None and (
            any(not item.strip() for item in value)
            or len(set(value)) != len(value)
        ):
            raise ValueError("OUTPUT_REQUIREMENT_ITEM_INVALID")
        return value

    @field_validator("language", "style")
    @classmethod
    def validate_nonblank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("OUTPUT_REQUIREMENT_TEXT_BLANK")
        return value


EntityCollection = Annotated[
    tuple[EntityV2, ...],
    Field(min_length=1, max_length=64),
]
EntityStateCollection = Annotated[tuple[EntityV2, ...], Field(max_length=64)]
TextStateCollection = Annotated[
    tuple[Annotated[str, Field(min_length=1, max_length=512)], ...],
    Field(max_length=64),
]
FieldPayload = (
    BoundedText
    | StrictBool
    | TemporalExpression
    | SourceConstraintsV2
    | OutputRequirementsV2
    | EntityCollection
    | BoundedTextCollection
)


class IntentParameterV2(_FrozenContract):
    """未绑定阶段允许携带的封闭通用参数。"""

    name: str = Field(min_length=1, max_length=128)
    value: ScalarValue


class GoalNodeV2(_FrozenContract):
    goal_id: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=2_000)
    candidate_capability_ids: tuple[str, ...] = Field(default=(), max_length=32)
    depends_on: tuple[str, ...] = Field(default=(), max_length=8)
    parameters: tuple[IntentParameterV2, ...] = Field(default=(), max_length=64)

    @field_validator("candidate_capability_ids", "depends_on")
    @classmethod
    def validate_identifier_list(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or len(item) > 128 for item in value):
            raise ValueError("IDENTIFIER_INVALID")
        if len(set(value)) != len(value):
            raise ValueError("IDENTIFIER_DUPLICATED")
        return value

    @field_validator("parameters")
    @classmethod
    def validate_unique_parameter_names(
        cls, value: tuple[IntentParameterV2, ...]
    ) -> tuple[IntentParameterV2, ...]:
        names = [item.name for item in value]
        if len(set(names)) != len(names):
            raise ValueError("PARAMETER_NAME_DUPLICATED")
        return value


class FieldOperation(_FrozenContract):
    operation: Literal["set", "clear", "append", "remove"]
    field_name: Literal[
        "topic",
        "entities",
        "exclusions",
        "temporal",
        "source_constraints",
        "output_requirements",
        "source_allowed_ids",
        "source_excluded_ids",
        "source_languages",
        "event_regions",
        "publisher_regions",
        "source_primary_only",
        "output_types",
        "target_platforms",
        "output_language",
        "output_style",
        "citations_required",
    ]
    value: FieldValue[FieldPayload] | None = None
    source_span: SourceSpan | None = None

    @model_validator(mode="after")
    def validate_operation_value(self) -> FieldOperation:
        """clear 是唯一不携带值的显式清空操作。"""

        if self.operation == "clear" and self.value is not None:
            raise ValueError("CLEAR_VALUE_FORBIDDEN")
        if self.operation != "clear" and self.value is None:
            raise ValueError("OPERATION_VALUE_REQUIRED")
        if self.operation == "clear" and self.source_span is None:
            raise ValueError("CLEAR_SOURCE_REQUIRED")
        if self.operation != "clear" and self.source_span is not None:
            raise ValueError("OPERATION_SOURCE_FORBIDDEN")
        return self


class IntentPatchV2(_FrozenContract):
    schema_version: Literal["intent-patch/2"] = "intent-patch/2"
    base_revision: StrictInt = Field(ge=0)
    dialog_act: Literal[
        "new_task",
        "answer_clarification",
        "refine",
        "follow_up",
        "cancel",
        "resume",
        "chat",
    ]
    goal_updates: tuple[GoalNodeV2, ...] = Field(default=(), max_length=8)
    field_operations: tuple[FieldOperation, ...] = Field(default=(), max_length=64)
    unresolved_references: tuple[str, ...] = Field(default=(), max_length=16)

    @field_validator("unresolved_references")
    @classmethod
    def validate_references(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or len(item) > 512 for item in value):
            raise ValueError("REFERENCE_INVALID")
        return value


class ValidatedIntentPatchV2(Protocol):
    """通过 I01 校验且绑定可信任务/消息范围的只读视图。"""

    @property
    def patch(self) -> IntentPatchV2 | None: ...

    @property
    def error_code(self) -> str | None: ...

    @property
    def trusted_task_id(self) -> str | None: ...

    @property
    def current_message_id(self) -> str | None: ...

    @property
    def visible_user_message_ids(self) -> frozenset[str]: ...


class IntentAmbiguityV2(_FrozenContract):
    field_name: str = Field(min_length=1, max_length=128)
    candidates: tuple[str, ...] = Field(min_length=2, max_length=16)
    execution_impact: str = Field(min_length=1, max_length=1_000)
    blocking: bool


class LeafFieldProvenanceV2(_FrozenContract):
    field_name: Literal[
        "source_allowed_ids",
        "source_excluded_ids",
        "source_languages",
        "event_regions",
        "publisher_regions",
        "source_primary_only",
        "output_types",
        "target_platforms",
        "output_language",
        "output_style",
        "citations_required",
    ]
    origin: Literal["explicit", "inherited", "default", "derived"]
    source_span: SourceSpan | None = None
    inherited_revision: StrictInt | None = Field(default=None, ge=0)
    normalizer_version: str | None = Field(default=None, min_length=1, max_length=64)
    default_policy_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_provenance(self) -> LeafFieldProvenanceV2:
        supplied = {
            "explicit": self.source_span is not None,
            "inherited": self.inherited_revision is not None,
            "default": self.default_policy_id is not None,
            "derived": self.normalizer_version is not None,
        }
        if not supplied[self.origin] or sum(supplied.values()) != 1:
            raise ValueError("LEAF_PROVENANCE_INVALID")
        return self


class IntentFrameV2(_FrozenContract):
    schema_version: Literal["intent-frame/2"] = "intent-frame/2"
    task_id: str = Field(min_length=1, max_length=128)
    revision: StrictInt = Field(ge=0)
    message_id: str = Field(min_length=1, max_length=128)
    anchor_time: datetime
    timezone: str = Field(min_length=1, max_length=128)
    dialog_act: Literal[
        "new_task",
        "answer_clarification",
        "refine",
        "follow_up",
        "cancel",
        "resume",
        "chat",
    ]
    goal_nodes: tuple[GoalNodeV2, ...] = Field(default=(), max_length=8)
    topic: FieldValue[BoundedText] | None = None
    entities: FieldValue[EntityStateCollection] | None = None
    exclusions: FieldValue[TextStateCollection] | None = None
    temporal: FieldValue[TemporalExpression] | None = None
    source_constraints: FieldValue[SourceConstraintsV2] | None = None
    output_requirements: FieldValue[OutputRequirementsV2] | None = None
    ambiguities: tuple[IntentAmbiguityV2, ...] = Field(default=(), max_length=32)
    unresolved_references: tuple[str, ...] = Field(default=(), max_length=16)
    leaf_provenance: tuple[LeafFieldProvenanceV2, ...] = Field(
        default=(), max_length=32
    )
    leaf_provenance_complete: StrictBool = False
    scope_hash: str = Field(
        default="",
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("TIMEZONE_INVALID") from exc
        return value

    @field_validator("anchor_time")
    @classmethod
    def validate_anchor(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ANCHOR_TIME_NAIVE")
        return value

    @field_validator("unresolved_references")
    @classmethod
    def validate_unresolved_references(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        if any(not item.strip() or len(item) > 512 for item in value):
            raise ValueError("REFERENCE_INVALID")
        return value

    @model_validator(mode="after")
    def validate_goal_graph(self) -> IntentFrameV2:
        _validate_dependency_graph(
            tuple((goal.goal_id, goal.depends_on) for goal in self.goal_nodes)
        )
        leaf_names = [item.field_name for item in self.leaf_provenance]
        if len(set(leaf_names)) != len(leaf_names):
            raise ValueError("LEAF_PROVENANCE_DUPLICATED")
        if not self.leaf_provenance_complete and leaf_names:
            raise ValueError("LEAF_PROVENANCE_PARTIAL_LEGACY")
        if self.leaf_provenance_complete:
            self._validate_complete_leaf_provenance(set(leaf_names))
        expected = self._calculate_scope_hash()
        if self.scope_hash and self.scope_hash != expected:
            raise ValueError("SCOPE_HASH_MISMATCH")
        object.__setattr__(self, "scope_hash", expected)
        return self

    def _validate_complete_leaf_provenance(self, known: set[str]) -> None:
        source_names = {
            "source_allowed_ids",
            "source_excluded_ids",
            "source_languages",
            "event_regions",
            "publisher_regions",
            "source_primary_only",
        }
        output_names = {
            "output_types",
            "target_platforms",
            "output_language",
            "output_style",
            "citations_required",
        }
        source = self.source_constraints.value if self.source_constraints else None
        output = self.output_requirements.value if self.output_requirements else None
        if source is None and known & source_names:
            raise ValueError("LEAF_PROVENANCE_WITHOUT_SOURCE")
        if output is None and known & output_names:
            raise ValueError("LEAF_PROVENANCE_WITHOUT_OUTPUT")
        required: set[str] = set()
        if source is not None:
            if source.allowed_source_ids is not None:
                required.add("source_allowed_ids")
            if source.excluded_source_ids:
                required.add("source_excluded_ids")
            if source.languages is not None:
                required.add("source_languages")
            if source.event_regions is not None:
                required.add("event_regions")
            if source.publisher_regions is not None:
                required.add("publisher_regions")
            if source.primary_only:
                required.add("source_primary_only")
        if output is not None:
            required.update(("output_types", "output_language"))
            if output.target_platforms is not None:
                required.add("target_platforms")
            if output.style is not None:
                required.add("output_style")
            if not output.citations_required:
                required.add("citations_required")
        if not required.issubset(known):
            raise ValueError("LEAF_PROVENANCE_INCOMPLETE")

    def _calculate_scope_hash(self) -> str:
        """仅对可执行语义范围生成稳定摘要，排除消息与来源元数据。"""

        payload: dict[str, object] = {
            "anchor_time": self.anchor_time.astimezone(UTC).isoformat(),
            "goal_nodes": [goal.model_dump(mode="json") for goal in self.goal_nodes],
            "topic": _field_semantic_value(self.topic),
            "entities": _field_semantic_value(self.entities),
            "exclusions": _field_semantic_value(self.exclusions),
            "temporal": _field_semantic_value(self.temporal),
            "timezone": self.timezone,
            "source_constraints": _field_semantic_value(self.source_constraints),
            "output_requirements": _field_semantic_value(self.output_requirements),
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CapabilityDescriptorV2(_FrozenContract):
    capability_id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=2_000)
    parameter_schema_ref: str = Field(min_length=1, max_length=256)
    required_permissions: tuple[str, ...] = Field(default=(), max_length=32)
    positive_examples: tuple[str, ...] = Field(default=(), max_length=16)
    negative_examples: tuple[str, ...] = Field(default=(), max_length=16)
    supported_outputs: tuple[str, ...] = Field(default=(), max_length=16)
    prerequisites: tuple[str, ...] = Field(default=(), max_length=16)


class CapabilityCatalogSnapshot(_FrozenContract):
    schema_version: Literal["capability-catalog/2"] = "capability-catalog/2"
    catalog_version: str = Field(min_length=1, max_length=128)
    capabilities: tuple[CapabilityDescriptorV2, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def validate_unique_capabilities(self) -> CapabilityCatalogSnapshot:
        identifiers = [item.capability_id for item in self.capabilities]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("CAPABILITY_DUPLICATED")
        return self


class CapabilityPlanStepV2(_FrozenContract):
    goal_id: str = Field(min_length=1, max_length=128)
    capability_id: str = Field(min_length=1, max_length=128)
    depends_on: tuple[str, ...] = Field(default=(), max_length=8)


class CapabilityPlanV2(_FrozenContract):
    schema_version: Literal["capability-plan/2"] = "capability-plan/2"
    steps: tuple[CapabilityPlanStepV2, ...] = Field(default=(), max_length=8)
    supported: bool = True
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_step_graph(self) -> CapabilityPlanV2:
        _validate_dependency_graph(
            tuple((step.goal_id, step.depends_on) for step in self.steps)
        )
        return self


class IntentDecision(_FrozenContract):
    schema_version: Literal["intent-decision/2"] = "intent-decision/2"
    outcome: Literal["READY", "CLARIFY", "UNSUPPORTED", "FAILED"]
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)
    clarification_fields: tuple[str, ...] = Field(default=(), max_length=16)


class IntentContextV2(_FrozenContract):
    current_message_id: BoundedIdentifier
    visible_message_ids: tuple[str, ...] = Field(default=(), max_length=128)
    context_version: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_message_scope(self) -> IntentContextV2:
        if any(not item.strip() or len(item) > 128 for item in self.visible_message_ids):
            raise ValueError("VISIBLE_MESSAGE_ID_INVALID")
        if len(set(self.visible_message_ids)) != len(self.visible_message_ids):
            raise ValueError("VISIBLE_MESSAGE_ID_DUPLICATED")
        if self.current_message_id not in self.visible_message_ids:
            raise ValueError("CURRENT_MESSAGE_NOT_VISIBLE")
        return self


class TrustedMessageV2(_FrozenContract):
    task_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=20_000)
    received_at: datetime
    timezone: str = Field(min_length=1, max_length=128)
    referenced_task_ids: tuple[BoundedIdentifier, ...] = Field(
        default=(), max_length=8
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("TIMEZONE_INVALID") from exc
        return value

    @field_validator("received_at")
    @classmethod
    def validate_received_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("RECEIVED_AT_NAIVE")
        return value

    @field_validator("referenced_task_ids")
    @classmethod
    def validate_referenced_tasks(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value) or len(set(value)) != len(value):
            raise ValueError("TASK_REFERENCE_INVALID")
        return value


def _field_semantic_value[T](value: FieldValue[T] | None) -> object:
    if value is None or value.value is None:
        return None
    field_value = value.value
    if isinstance(field_value, BaseModel):
        return field_value.model_dump(mode="json")
    if isinstance(field_value, tuple):
        return [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for item in field_value
        ]
    return field_value


class PermissionSnapshotV2(_FrozenContract):
    version: str = Field(min_length=1, max_length=128)
    allowed_capability_ids: tuple[str, ...] = Field(default=(), max_length=256)


class BudgetLeaseReferenceV2(_FrozenContract):
    lease_id: str = Field(min_length=1, max_length=128)
    version: StrictInt = Field(ge=0)


def _validate_dependency_graph(
    nodes: tuple[tuple[str, tuple[str, ...]], ...],
) -> None:
    """验证标识唯一、依赖存在且有向图无环。"""

    identifiers = [identifier for identifier, _ in nodes]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("GOAL_ID_DUPLICATED")
    known = set(identifiers)
    graph = {identifier: dependencies for identifier, dependencies in nodes}
    if any(dependency not in known for dependencies in graph.values() for dependency in dependencies):
        raise ValueError("GOAL_DEPENDENCY_UNKNOWN")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise ValueError("GOAL_DEPENDENCY_CYCLE")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in graph[identifier]:
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in identifiers:
        visit(identifier)


__all__ = [
    "BoundedIdentifier",
    "BoundedText",
    "BoundedTextCollection",
    "BudgetLeaseReferenceV2",
    "CapabilityCatalogSnapshot",
    "CapabilityDescriptorV2",
    "CapabilityPlanStepV2",
    "CapabilityPlanV2",
    "EntityCollection",
    "EntityStateCollection",
    "EntityV2",
    "FieldOperation",
    "FieldPayload",
    "FieldValue",
    "GoalNodeV2",
    "IntentAmbiguityV2",
    "IntentContextV2",
    "IntentDecision",
    "IntentFrameV2",
    "IntentParameterV2",
    "IntentPatchV2",
    "LeafFieldProvenanceV2",
    "OutputRequirementsV2",
    "PermissionSnapshotV2",
    "SourceConstraintsV2",
    "SourceSpan",
    "TextStateCollection",
    "TrustedMessageV2",
    "ValidatedIntentPatchV2",
]
