"""把开放意图限制为显式注册的运营场景。"""

from __future__ import annotations

from dataclasses import dataclass

from efficiency_platform_agent.agents.operation.contracts.profiles import ProfileKind
from efficiency_platform_agent.agents.operation.scenarios.contracts import (
    ScenarioPackRegistry,
)
from efficiency_platform_agent.agents.operation.scenarios.manifests import (
    build_s6_manifests,
)
from efficiency_platform_agent.agents.operation.scenarios.registry import (
    InMemoryScenarioPackRegistry,
)
from efficiency_platform_agent.contracts.intent import IntentEnvelopeV1

_ALIASES = {
    "research": "industry_digest",
    "industry_research": "industry_digest",
    "content": "multi_platform_content",
    "content_creation": "multi_platform_content",
    "multi_platform": "multi_platform_content",
    "brand": "brand_operation_plan",
    "brand_plan": "brand_operation_plan",
    "ip": "ip_operation_plan",
    "ip_plan": "ip_operation_plan",
    "campaign": "campaign_plan",
    "campaign_planning": "campaign_plan",
    "calendar": "content_calendar",
    "content_planning": "content_calendar",
    "growth": "growth_experiment",
    "growth_plan": "growth_experiment",
    "review": "operation_review",
    "analytics_review": "operation_review",
}

_CONDITION_FIELDS = {
    "topic": "topic",
    "time-window": "time_window",
    "platforms": "platforms",
    "brand": "brand",
    "goal": "goal",
    "planning-window": "planning_window",
    "ip": "ip",
    "audience": "audience",
    "incubation-window": "incubation_window",
    "campaign-goal": "campaign_goal",
    "campaign-window": "campaign_window",
    "topic-scope": "topic_scope",
    "calendar-window": "calendar_window",
    "growth-goal": "growth_goal",
    "funnel-stage": "funnel_stage",
    "experiment-window": "experiment_window",
    "review-window": "review_window",
    "metric-definition": "metric_definition",
}

_PROFILE_FIELDS = {
    ProfileKind.BRAND: "brand",
    ProfileKind.IP: "ip",
    ProfileKind.PRODUCT: "product",
    ProfileKind.AUDIENCE: "audience",
    ProfileKind.METRIC: "metric_definition",
    ProfileKind.CHANNEL: "platforms",
    ProfileKind.CAMPAIGN: "campaign_goal",
}

ScenarioConditionValue = str | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolvedScenarioCondition:
    """一个 Manifest 条件及其来自受控意图字段的值。"""

    condition_id: str
    value: ScenarioConditionValue


@dataclass(frozen=True, slots=True)
class ScenarioResolution:
    """场景匹配结果；调用方必须检查 executable 后才能执行。"""

    scenario_id: str | None
    semantic_version: str | None
    executable: bool
    needs_clarification: bool
    reason_code: str
    condition_values: tuple[ResolvedScenarioCondition, ...] = ()
    missing_condition_ids: tuple[str, ...] = ()
    required_profile_kinds: tuple[ProfileKind, ...] = ()
    missing_profile_fields: tuple[str, ...] = ()


class ScenarioResolver:
    """只查询注入的场景注册表，不创建动态场景或执行节点。"""

    def __init__(
        self,
        registry: ScenarioPackRegistry | None = None,
        *,
        confidence_threshold: float = 0.65,
    ) -> None:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold必须在0到1之间")
        self.registry = registry or InMemoryScenarioPackRegistry(build_s6_manifests())
        self.confidence_threshold = confidence_threshold

    def resolve(self, intent: IntentEnvelopeV1) -> ScenarioResolution:
        """精确或按显式别名匹配；未知候选稳定拒绝。"""
        if not isinstance(intent, IntentEnvelopeV1):
            raise TypeError("intent必须是IntentEnvelopeV1")
        raw_candidate = intent.task_type.strip().lower().replace("-", "_")
        candidate = _ALIASES.get(raw_candidate, raw_candidate)
        manifests = tuple(
            item for item in self.registry.list() if item.scenario_id == candidate
        )
        if not manifests:
            return ScenarioResolution(None, None, False, False, "UNKNOWN_SCENARIO")
        manifest = manifests[-1]
        required_in_order = tuple(
            item.condition_id
            for item in manifest.trigger_conditions
            if item.condition_id in manifest.required_condition_ids
        )
        condition_values = self._condition_values(intent, required_in_order)
        available = {item.condition_id for item in condition_values}
        declared_missing = {
            item.strip().lower().replace("_", "-") for item in intent.missing_fields
        }
        missing_conditions = tuple(
            item.condition_id
            for item in manifest.trigger_conditions
            if item.condition_id in manifest.required_condition_ids
            and (
                item.condition_id not in available
                or item.condition_id in declared_missing
            )
        )
        profile_kinds = tuple(sorted(manifest.profile_requirements, key=str))
        missing_profile_fields = tuple(
            _PROFILE_FIELDS[kind]
            for kind in profile_kinds
            if (
                not getattr(intent.requirements, _PROFILE_FIELDS[kind])
                or _PROFILE_FIELDS[kind].replace("_", "-") in declared_missing
            )
        )
        common = (
            condition_values,
            missing_conditions,
            profile_kinds,
            missing_profile_fields,
        )
        if missing_conditions:
            return ScenarioResolution(
                manifest.scenario_id,
                manifest.semantic_version,
                False,
                True,
                "MISSING_REQUIRED_CONDITIONS",
                *common,
            )
        if missing_profile_fields:
            return ScenarioResolution(
                manifest.scenario_id,
                manifest.semantic_version,
                False,
                True,
                "MISSING_REQUIRED_PROFILE_FIELDS",
                *common,
            )
        if intent.missing_fields or intent.needs_clarification:
            return ScenarioResolution(
                manifest.scenario_id,
                manifest.semantic_version,
                False,
                True,
                "NEEDS_CLARIFICATION",
                *common,
            )
        if intent.confidence < self.confidence_threshold:
            return ScenarioResolution(
                manifest.scenario_id,
                manifest.semantic_version,
                False,
                True,
                "LOW_CONFIDENCE",
                *common,
            )
        return ScenarioResolution(
            manifest.scenario_id,
            manifest.semantic_version,
            True,
            False,
            "MATCHED",
            *common,
        )

    @staticmethod
    def _condition_values(
        intent: IntentEnvelopeV1, required_condition_ids: tuple[str, ...]
    ) -> tuple[ResolvedScenarioCondition, ...]:
        """只读取显式映射字段，避免把概括性 goal 猜成多个不同条件。"""
        requirements = intent.requirements
        values: list[ResolvedScenarioCondition] = []
        for condition_id in required_condition_ids:
            field_name = _CONDITION_FIELDS.get(condition_id)
            if field_name is None:
                continue
            value = getattr(requirements, field_name)
            if value is None or value == ():
                continue
            values.append(ResolvedScenarioCondition(condition_id, value))
        return tuple(values)


__all__ = [
    "ResolvedScenarioCondition",
    "ScenarioConditionValue",
    "ScenarioResolution",
    "ScenarioResolver",
]
