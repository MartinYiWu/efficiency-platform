"""受控运营场景解析的离线测试。"""

import pytest

from efficiency_platform_agent.agents.operation.scenarios.manifests import (
    build_s6_manifests,
)
from efficiency_platform_agent.agents.operation.scenarios.registry import (
    InMemoryScenarioPackRegistry,
)
from efficiency_platform_agent.contracts.intent import (
    IntentEnvelopeV1,
    IntentRequirementsV1,
)

_SCENARIO_MATRIX = (
    (
        "industry_digest",
        {"topic": "AI Agent", "time_window": "最近30天"},
        ("topic", "time-window"),
        (),
    ),
    (
        "multi_platform_content",
        {"topic": "效率工具", "platforms": ("xiaohongshu", "wechat")},
        ("topic", "platforms"),
        ("channel",),
    ),
    (
        "brand_operation_plan",
        {
            "brand": "效率品牌",
            "product": "效率工作台",
            "goal": "提升认知",
            "planning_window": "Q4",
        },
        ("brand", "goal", "planning-window"),
        ("brand", "product"),
    ),
    (
        "ip_operation_plan",
        {"ip": "效率教练", "audience": "职场新人", "incubation_window": "90天"},
        ("ip", "audience", "incubation-window"),
        ("audience", "ip"),
    ),
    (
        "campaign_plan",
        {
            "campaign_goal": "获得1000条线索",
            "audience": "中小企业主",
            "campaign_window": "双十一",
        },
        ("campaign-goal", "audience", "campaign-window"),
        ("audience", "campaign"),
    ),
    (
        "content_calendar",
        {"topic_scope": "AI效率", "calendar_window": "2026年10月"},
        ("topic-scope", "calendar-window"),
        (),
    ),
    (
        "growth_experiment",
        {
            "growth_goal": "注册转化提升10%",
            "funnel_stage": "激活",
            "experiment_window": "4周",
        },
        ("growth-goal", "funnel-stage", "experiment-window"),
        (),
    ),
    (
        "operation_review",
        {"review_window": "2026年Q3", "metric_definition": "有效线索率"},
        ("review-window", "metric-definition"),
        ("metric",),
    ),
)


def _intent(
    task_type: str,
    *,
    confidence: float = 0.95,
    missing_fields: list[str] | None = None,
    needs_clarification: bool = False,
    requirements: dict[str, object] | None = None,
) -> IntentEnvelopeV1:
    return IntentEnvelopeV1(
        domain="运营",
        goal="生成运营交付物",
        task_type=task_type,
        channels=["xiaohongshu"],
        missing_fields=missing_fields or [],
        needs_clarification=needs_clarification,
        confidence=confidence,
        requirements=IntentRequirementsV1(**(requirements or {})),
    )


def _resolver():
    from efficiency_platform_agent.orchestration.scenario_resolver import (
        ScenarioResolver,
    )

    registry = InMemoryScenarioPackRegistry(build_s6_manifests())
    return ScenarioResolver(registry)


def test_complete_request_resolves_to_registered_scenario() -> None:
    resolution = _resolver().resolve(
        _intent(
            "multi_platform_content",
            requirements={"topic": "新品", "platforms": ("xiaohongshu",)},
        )
    )

    assert resolution.executable is True
    assert resolution.scenario_id == "multi_platform_content"
    assert resolution.semantic_version == "1.0.0"
    assert resolution.reason_code == "MATCHED"


def test_controlled_alias_resolves_without_dynamic_scenario_creation() -> None:
    resolution = _resolver().resolve(
        _intent(
            "content",
            requirements={"topic": "新品", "platforms": ("xiaohongshu",)},
        )
    )

    assert resolution.executable is True
    assert resolution.scenario_id == "multi_platform_content"


def test_unknown_scenario_candidate_is_rejected() -> None:
    resolution = _resolver().resolve(_intent("invented_dynamic_scenario"))

    assert resolution.executable is False
    assert resolution.scenario_id is None
    assert resolution.semantic_version is None
    assert resolution.reason_code == "UNKNOWN_SCENARIO"


def test_missing_information_requires_clarification_before_execution() -> None:
    resolution = _resolver().resolve(
        _intent(
            "multi_platform_content",
            missing_fields=["product"],
            needs_clarification=True,
            requirements={"topic": "新品", "platforms": ("xiaohongshu",)},
        )
    )

    assert resolution.executable is False
    assert resolution.needs_clarification is True
    assert resolution.scenario_id == "multi_platform_content"
    assert resolution.reason_code == "NEEDS_CLARIFICATION"


def test_low_confidence_requires_clarification_before_execution() -> None:
    resolution = _resolver().resolve(
        _intent(
            "campaign_plan",
            confidence=0.4,
            requirements={
                "campaign_goal": "获客",
                "audience": "职场人",
                "campaign_window": "本月",
            },
        )
    )

    assert resolution.executable is False
    assert resolution.needs_clarification is True
    assert resolution.reason_code == "LOW_CONFIDENCE"


@pytest.mark.parametrize(
    ("scenario_id", "requirements", "condition_ids", "profile_kinds"),
    _SCENARIO_MATRIX,
)
def test_all_scenarios_resolve_complete_controlled_requirements(
    scenario_id: str,
    requirements: dict[str, object],
    condition_ids: tuple[str, ...],
    profile_kinds: tuple[str, ...],
) -> None:
    resolution = _resolver().resolve(_intent(scenario_id, requirements=requirements))

    assert resolution.executable is True
    assert (
        tuple(item.condition_id for item in resolution.condition_values)
        == condition_ids
    )
    assert resolution.missing_condition_ids == ()
    assert resolution.missing_profile_fields == ()
    assert (
        tuple(item.value for item in resolution.required_profile_kinds) == profile_kinds
    )


def test_brand_plan_missing_product_is_rejected_by_resolver_before_conversation() -> (
    None
):
    resolution = _resolver().resolve(
        _intent(
            "brand_operation_plan",
            requirements={
                "brand": "效率品牌",
                "goal": "提升认知",
                "planning_window": "Q4",
            },
        )
    )

    assert resolution.executable is False
    assert resolution.needs_clarification is True
    assert resolution.reason_code == "MISSING_REQUIRED_PROFILE_FIELDS"
    assert resolution.missing_condition_ids == ()
    assert resolution.missing_profile_fields == ("product",)


@pytest.mark.parametrize(
    ("scenario_id", "requirements", "condition_ids", "profile_kinds"),
    _SCENARIO_MATRIX,
)
def test_all_scenarios_request_clarification_when_one_required_field_is_missing(
    scenario_id: str,
    requirements: dict[str, object],
    condition_ids: tuple[str, ...],
    profile_kinds: tuple[str, ...],
) -> None:
    incomplete = dict(requirements)
    missing_field = condition_ids[-1].replace("-", "_")
    incomplete.pop(missing_field)

    resolution = _resolver().resolve(_intent(scenario_id, requirements=incomplete))

    assert resolution.executable is False
    assert resolution.needs_clarification is True
    assert resolution.reason_code == "MISSING_REQUIRED_CONDITIONS"
    assert resolution.missing_condition_ids == (condition_ids[-1],)
    assert (
        tuple(item.value for item in resolution.required_profile_kinds) == profile_kinds
    )
