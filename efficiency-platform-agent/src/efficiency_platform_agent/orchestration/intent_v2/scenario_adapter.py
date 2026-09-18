"""Intent V2 到旧场景协调层的无损、不可执行投影。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)
from efficiency_platform_agent.contracts.intent_v2 import (
    CapabilityPlanV2,
    EntityV2,
    FieldValue,
    IntentFrameV2,
    IntentParameterV2,
    OutputRequirementsV2,
    SourceConstraintsV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import TemporalExpression


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScenarioProjectionParametersV2(_FrozenContract):
    topic: str | None = None
    entities: tuple[EntityV2, ...] = Field(default=(), max_length=64)
    exclusions: tuple[str, ...] = Field(default=(), max_length=64)
    temporal: TemporalExpression | None = None
    source_constraints: SourceConstraintsV2 | None = None
    output_requirements: OutputRequirementsV2 | None = None
    intent_parameters: tuple[IntentParameterV2, ...] = Field(default=(), max_length=64)


class ScenarioProjectionStepV2(_FrozenContract):
    goal_id: str = Field(min_length=1, max_length=128)
    capability_id: str = Field(min_length=1, max_length=128)
    depends_on: tuple[str, ...] = Field(default=(), max_length=8)
    parameters: ScenarioProjectionParametersV2


class ScenarioProjectionV2(_FrozenContract):
    schema_version: Literal["scenario-projection/2"] = "scenario-projection/2"
    intent_revision: int = Field(ge=0)
    scope_hash: str = Field(min_length=64, max_length=64)
    supported: bool
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)
    steps: tuple[ScenarioProjectionStepV2, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def validate_outcome(self) -> ScenarioProjectionV2:
        if self.supported and (not self.steps or self.reason_codes):
            raise ValueError("SCENARIO_PROJECTION_SUPPORTED_INVALID")
        if not self.supported and (self.steps or not self.reason_codes):
            raise ValueError("SCENARIO_PROJECTION_UNSUPPORTED_INVALID")
        return self


class ScenarioInputAdapter:
    """保留复合 Goal，不构造 V1 envelope 或执行任务。"""

    def project(
        self,
        frame: IntentFrameV2,
        capability_plan: CapabilityPlanV2,
    ) -> ScenarioProjectionV2:
        if not isinstance(frame, IntentFrameV2):
            raise TypeError("frame 必须是 IntentFrameV2")
        if not isinstance(capability_plan, CapabilityPlanV2):
            raise TypeError("capability_plan 必须是 CapabilityPlanV2")
        if not capability_plan.supported:
            return _unsupported(
                frame,
                capability_plan.reason_codes or ("SCENARIO_PLAN_UNSUPPORTED",),
            )
        if frame.unresolved_references or any(
            item.blocking for item in frame.ambiguities
        ):
            return _unsupported(frame, ("SCENARIO_INTENT_NOT_READY",))
        if capability_plan.reason_codes:
            return _unsupported(frame, ("SCENARIO_PLAN_INCONSISTENT",))
        expected_ids = {goal.goal_id for goal in frame.goal_nodes}
        planned_ids = {step.goal_id for step in capability_plan.steps}
        if not expected_ids or planned_ids != expected_ids:
            return _unsupported(frame, ("SCENARIO_PLAN_INCOMPLETE",))
        goal_by_id = {goal.goal_id: goal for goal in frame.goal_nodes}
        known_capabilities = {item.value for item in OperationSpecialistCapabilityId}
        if any(
            step.capability_id not in known_capabilities
            for step in capability_plan.steps
        ):
            return _unsupported(frame, ("SCENARIO_CAPABILITY_UNSUPPORTED",))
        if any(
            step.capability_id not in goal_by_id[step.goal_id].candidate_capability_ids
            for step in capability_plan.steps
        ):
            return _unsupported(frame, ("SCENARIO_CAPABILITY_MISMATCH",))
        if any(
            step.depends_on != goal_by_id[step.goal_id].depends_on
            for step in capability_plan.steps
        ):
            return _unsupported(frame, ("SCENARIO_DEPENDENCY_MISMATCH",))
        try:
            shared = ScenarioProjectionParametersV2(
                topic=_project_value(frame.topic),
                entities=_project_value(frame.entities) or (),
                exclusions=_project_value(frame.exclusions) or (),
                temporal=_project_value(frame.temporal),
                source_constraints=_project_value(frame.source_constraints),
                output_requirements=_project_value(frame.output_requirements),
            )
        except ValueError:
            return _unsupported(frame, ("SCENARIO_PARAMETERS_INVALID",))
        steps = tuple(
            ScenarioProjectionStepV2(
                goal_id=step.goal_id,
                capability_id=step.capability_id,
                depends_on=step.depends_on,
                parameters=shared.model_copy(
                    update={"intent_parameters": goal_by_id[step.goal_id].parameters}
                ),
            )
            for step in capability_plan.steps
        )
        return ScenarioProjectionV2(
            intent_revision=frame.revision,
            scope_hash=frame.scope_hash,
            supported=True,
            steps=steps,
        )


def _project_value[T](field: FieldValue[T] | None) -> T | None:
    if field is None:
        return None
    if field.validation != "valid":
        raise ValueError("SCENARIO_FIELD_INVALID")
    return field.value


def _unsupported(
    frame: IntentFrameV2,
    reason_codes: tuple[str, ...],
) -> ScenarioProjectionV2:
    return ScenarioProjectionV2(
        intent_revision=frame.revision,
        scope_hash=frame.scope_hash,
        supported=False,
        reason_codes=reason_codes,
    )


__all__ = [
    "ScenarioInputAdapter",
    "ScenarioProjectionParametersV2",
    "ScenarioProjectionStepV2",
    "ScenarioProjectionV2",
]
