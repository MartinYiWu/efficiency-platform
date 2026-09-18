"""Intent V2 的确定性能力、权限、参数和 DAG 绑定。"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)
from efficiency_platform_agent.contracts.intent_v2 import (
    CapabilityCatalogSnapshot,
    CapabilityPlanStepV2,
    CapabilityPlanV2,
    GoalNodeV2,
    IntentFrameV2,
    IntentParameterV2,
    PermissionSnapshotV2,
)

type ParameterValueType = Literal["string", "integer", "number", "boolean"]

_FRAME_FIELDS = frozenset(
    {
        "topic",
        "entities",
        "exclusions",
        "temporal",
        "source_constraints",
        "output_requirements",
        "goal_nodes",
    }
)


@dataclass(frozen=True, slots=True)
class ParameterRuleV2:
    name: str
    value_type: ParameterValueType
    required: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("parameter name 必须是非空字符串")
        if self.value_type not in {"string", "integer", "number", "boolean"}:
            raise ValueError("parameter value_type 无效")
        if not isinstance(self.required, bool):
            raise TypeError("parameter required 必须是 bool")


@dataclass(frozen=True, slots=True)
class CapabilityParameterSchemaV2:
    schema_ref: str
    parameter_rules: tuple[ParameterRuleV2, ...] = ()
    required_frame_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.schema_ref, str) or not self.schema_ref.strip():
            raise ValueError("schema_ref 必须是非空字符串")
        names = [item.name for item in self.parameter_rules]
        if len(set(names)) != len(names):
            raise ValueError("PARAMETER_RULE_DUPLICATED")
        if len(set(self.required_frame_fields)) != len(self.required_frame_fields):
            raise ValueError("REQUIRED_FRAME_FIELD_DUPLICATED")
        if any(item not in _FRAME_FIELDS for item in self.required_frame_fields):
            raise ValueError("REQUIRED_FRAME_FIELD_UNKNOWN")


class CapabilityParameterSchemaRegistry:
    """显式参数 Schema 索引；只校验，不拥有执行能力。"""

    def __init__(self, schemas: tuple[CapabilityParameterSchemaV2, ...]) -> None:
        if not isinstance(schemas, tuple):
            raise TypeError("schemas 必须是 tuple")
        mapping = {item.schema_ref: item for item in schemas}
        if len(mapping) != len(schemas):
            raise ValueError("CAPABILITY_PARAMETER_SCHEMA_DUPLICATED")
        self._schemas = MappingProxyType(mapping)

    def get(self, schema_ref: str) -> CapabilityParameterSchemaV2 | None:
        return self._schemas.get(schema_ref)


class CapabilityBinderV2:
    """仅把显式 Goal 候选绑定到已注册、已授权且参数合法的能力。"""

    def __init__(self, schemas: CapabilityParameterSchemaRegistry) -> None:
        if not isinstance(schemas, CapabilityParameterSchemaRegistry):
            raise TypeError("schemas 必须是 CapabilityParameterSchemaRegistry")
        self.schemas = schemas

    def bind(
        self,
        frame: IntentFrameV2,
        catalog: CapabilityCatalogSnapshot,
        permissions: PermissionSnapshotV2,
    ) -> CapabilityPlanV2:
        if not isinstance(frame, IntentFrameV2):
            raise TypeError("frame 必须是 IntentFrameV2")
        if not isinstance(catalog, CapabilityCatalogSnapshot):
            raise TypeError("catalog 必须是 CapabilityCatalogSnapshot")
        if not isinstance(permissions, PermissionSnapshotV2):
            raise TypeError("permissions 必须是 PermissionSnapshotV2")
        descriptors = {item.capability_id: item for item in catalog.capabilities}
        referenced = {
            capability_id
            for goal in frame.goal_nodes
            for capability_id in goal.candidate_capability_ids
        }
        if any(item not in descriptors for item in referenced) or any(
            not goal.candidate_capability_ids for goal in frame.goal_nodes
        ):
            return _unsupported("CAPABILITY_UNKNOWN")

        selected: dict[str, str] = {}
        allowed = set(permissions.allowed_capability_ids)
        for goal in frame.goal_nodes:
            capability_id = next(
                (item for item in goal.candidate_capability_ids if item in allowed),
                None,
            )
            if capability_id is None:
                return _unsupported("CAPABILITY_UNAVAILABLE")
            descriptor = descriptors[capability_id]
            schema = self.schemas.get(descriptor.parameter_schema_ref)
            if schema is None:
                return _unsupported("CAPABILITY_SCHEMA_UNKNOWN")
            if not _parameters_valid(goal.parameters, schema):
                return _unsupported("CAPABILITY_PARAMETER_INVALID")
            missing = tuple(
                field_name
                for field_name in schema.required_frame_fields
                if not _frame_field_present(frame, field_name)
            )
            if missing:
                return CapabilityPlanV2(
                    supported=False,
                    reason_codes=tuple(
                        f"REQUIRED_FIELD_MISSING:{item}" for item in missing
                    ),
                )
            selected[goal.goal_id] = capability_id

        ordered = _stable_topological_order(frame.goal_nodes)
        return CapabilityPlanV2(
            steps=tuple(
                CapabilityPlanStepV2(
                    goal_id=goal.goal_id,
                    capability_id=selected[goal.goal_id],
                    depends_on=goal.depends_on,
                )
                for goal in ordered
            )
        )


def build_operation_parameter_schema_registry() -> CapabilityParameterSchemaRegistry:
    """构造与真实运营能力一一对应的 Intent 阶段参数 Schema。"""
    required_by_capability: dict[str, tuple[str, ...]] = {
        OperationSpecialistCapabilityId.RESEARCH_INSIGHT.value: (
            "topic",
            "temporal",
            "source_constraints",
            "output_requirements",
        ),
        OperationSpecialistCapabilityId.CHANNEL_CONTENT.value: (
            "topic",
            "output_requirements",
        ),
        OperationSpecialistCapabilityId.CONTENT_CREATE.value: ("topic",),
        OperationSpecialistCapabilityId.ANALYTICS_REVIEW.value: ("temporal",),
    }
    common_rules = (
        ParameterRuleV2("count", "integer"),
        ParameterRuleV2("objective", "string"),
    )
    return CapabilityParameterSchemaRegistry(
        tuple(
            CapabilityParameterSchemaV2(
                schema_ref=f"operation-intent-parameters/{capability.value}/1",
                parameter_rules=common_rules,
                required_frame_fields=required_by_capability.get(capability.value, ()),
            )
            for capability in OperationSpecialistCapabilityId
        )
    )


def _unsupported(reason: str) -> CapabilityPlanV2:
    return CapabilityPlanV2(supported=False, reason_codes=(reason,))


def _parameters_valid(
    parameters: tuple[IntentParameterV2, ...],
    schema: CapabilityParameterSchemaV2,
) -> bool:
    rules = {item.name: item for item in schema.parameter_rules}
    supplied = {item.name: item.value for item in parameters}
    if any(name not in rules for name in supplied):
        return False
    if any(rule.required and rule.name not in supplied for rule in rules.values()):
        return False
    return all(
        _strict_type(supplied[name], rules[name].value_type) for name in supplied
    )


def _strict_type(value: object, value_type: ParameterValueType) -> bool:
    if value_type == "string":
        return isinstance(value, str)
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _frame_field_present(frame: IntentFrameV2, field_name: str) -> bool:
    if field_name == "goal_nodes":
        return bool(frame.goal_nodes)
    value = getattr(frame, field_name)
    return value is not None and value.value is not None and value.validation == "valid"


def _stable_topological_order(
    goals: tuple[GoalNodeV2, ...],
) -> tuple[GoalNodeV2, ...]:
    pending = list(goals)
    completed: set[str] = set()
    result: list[GoalNodeV2] = []
    while pending:
        ready = [goal for goal in pending if set(goal.depends_on) <= completed]
        if not ready:  # IntentFrameV2 已校验 DAG；防御 bypass 构造。
            raise ValueError("GOAL_DEPENDENCY_CYCLE")
        for goal in ready:
            pending.remove(goal)
            result.append(goal)
            completed.add(goal.goal_id)
    return tuple(result)


__all__ = [
    "CapabilityBinderV2",
    "CapabilityParameterSchemaRegistry",
    "CapabilityParameterSchemaV2",
    "ParameterRuleV2",
    "build_operation_parameter_schema_registry",
]
