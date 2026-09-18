"""八个运营场景包的显式 S3 Manifest 声明。"""

from __future__ import annotations

from efficiency_platform_agent.agents.operation.contracts.planning import (
    FailureBehavior,
)
from efficiency_platform_agent.agents.operation.contracts.profiles import ProfileKind
from efficiency_platform_agent.agents.operation.contracts.scenarios import (
    ClarificationPolicy,
    PlanTemplateDefinition,
    ScenarioPackManifest,
    ScenarioStepDefinition,
)
from efficiency_platform_agent.agents.operation.contracts.task import (
    ConditionImportance,
    DeliverableKind,
    DeliverableRequirement,
    KeyCondition,
    OperationIntent,
)
from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId as C,
)
from efficiency_platform_agent.core.agent import CapabilityRequirement
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.run import ExecutionBudget

QUALITY_CHECKS = frozenset(
    {
        "q.required-deliverables/1",
        "q.evidence-linkage/1",
        "q.profile-authority/1",
        "q.assumption-disclosure/1",
        "q.metrics-definition/1",
        "q.partial-scope/1",
        "q.channel-independence/1",
        "q.no-publication/1",
        "q.review-round-limit/1",
    }
)
# 外部模型首字节和多平台并行生成存在网络抖动，平台阶段保留独立的 120 秒上限；
# 总 Run 预算仍由组合根统一约束，避免单个平台无限等待。
# 多平台平台正文和结构化 JSON 需要完整输出，避免 2,000 Token 旧上限截断。
_BUDGET = ExecutionBudget(4, 1, 4000, 8000, 120000, 0)
_RESEARCH_BUDGET = ExecutionBudget(4, 1, 4000, 8000, 240000, 0)
_TERMINATION = frozenset({"stop_on_failure"})


def _condition(condition_id: str) -> KeyCondition:
    return KeyCondition(
        condition_id, condition_id.replace("-", " "), ConditionImportance.CRITICAL, None
    )


def _requirement(
    requirement_id: str,
    kind: DeliverableKind = DeliverableKind.REPORT,
    channels: tuple[str, ...] = (),
) -> DeliverableRequirement:
    return DeliverableRequirement(
        requirement_id, kind, 1, channels, "markdown", "standard", QUALITY_CHECKS
    )


def _step(
    step_id: str,
    task_type: str,
    capability: C,
    outputs: tuple[str, ...],
    depends: tuple[str, ...] = (),
    budget: ExecutionBudget = _BUDGET,
) -> ScenarioStepDefinition:
    return ScenarioStepDefinition(
        "scenario-step/1",
        "1.0.0",
        step_id,
        task_type,
        depends,
        CapabilityRequirement(all_of=frozenset({capability.value})),
        "operation-specialist-input/1",
        "operation-specialist-result/1",
        (),
        frozenset(),
        frozenset(),
        budget,
        outputs,
        QUALITY_CHECKS,
        True,
        FailureBehavior.FAIL,
    )


def _manifest(
    scenario_id: str,
    intent: OperationIntent,
    conditions: tuple[str, ...],
    steps: tuple[ScenarioStepDefinition, ...],
    outputs: tuple[DeliverableRequirement, ...],
    profiles: frozenset[ProfileKind] = frozenset(),
    budget: ExecutionBudget = _BUDGET,
) -> ScenarioPackManifest:
    termination = _TERMINATION
    template = PlanTemplateDefinition(
        "plan-template/1",
        f"{scenario_id}-template",
        "1.0.0",
        ("all_required_steps_succeeded",),
        steps,
        termination,
    )
    return ScenarioPackManifest(
        "scenario-pack/1",
        scenario_id,
        "1.0.0",
        frozenset({intent}),
        tuple(_condition(item) for item in conditions),
        frozenset(conditions),
        (),
        ClarificationPolicy.ASK_IF_REQUIRED_MISSING,
        StrategyMode.WORKFLOW,
        template,
        profiles,
        outputs,
        QUALITY_CHECKS,
        budget,
        termination,
        FailureBehavior.FAIL,
    )


INDUSTRY_DIGEST_PACK_V1 = _manifest(
    "industry_digest",
    OperationIntent.RESEARCH,
    ("topic", "time-window"),
    (
        _step(
            "research",
            "operation.research",
            C.RESEARCH_INSIGHT,
            ("industry-report",),
            budget=_RESEARCH_BUDGET,
        ),
    ),
    (_requirement("industry-report"),),
    budget=_RESEARCH_BUDGET,
)

MULTI_PLATFORM_CONTENT_PACK_V1 = _manifest(
    "multi_platform_content",
    OperationIntent.CREATE,
    ("topic", "platforms"),
    (
        _step(
            "xiaohongshu",
            "operation.channel_content",
            C.CHANNEL_CONTENT,
            ("platform-content-xiaohongshu",),
        ),
        _step(
            "wechat-official-account",
            "operation.channel_content",
            C.CHANNEL_CONTENT,
            ("platform-content-wechat-official-account",),
        ),
        _step(
            "toutiao",
            "operation.channel_content",
            C.CHANNEL_CONTENT,
            ("platform-content-toutiao",),
        ),
    ),
    (
        _requirement(
            "platform-content-xiaohongshu", DeliverableKind.COPY, ("xiaohongshu",)
        ),
        _requirement(
            "platform-content-wechat-official-account",
            DeliverableKind.COPY,
            ("wechat_official_account",),
        ),
        _requirement("platform-content-toutiao", DeliverableKind.COPY, ("toutiao",)),
    ),
    frozenset({ProfileKind.CHANNEL}),
)

BRAND_OPERATION_PLAN_PACK_V1 = _manifest(
    "brand_operation_plan",
    OperationIntent.PLAN,
    ("brand", "goal", "planning-window"),
    (
        _step(
            "brand-strategy",
            "operation.brand_strategy",
            C.BRAND_STRATEGY,
            ("brand-strategy",),
        ),
    ),
    (_requirement("brand-strategy", DeliverableKind.PLAN),),
    frozenset({ProfileKind.BRAND, ProfileKind.PRODUCT}),
)

IP_OPERATION_PLAN_PACK_V1 = _manifest(
    "ip_operation_plan",
    OperationIntent.PLAN,
    ("ip", "audience", "incubation-window"),
    (
        _step(
            "ip-strategy", "operation.ip_strategy", C.IP_STRATEGY, ("ip-positioning",)
        ),
    ),
    (_requirement("ip-positioning", DeliverableKind.PLAN),),
    frozenset({ProfileKind.IP, ProfileKind.AUDIENCE}),
)

CAMPAIGN_PLAN_PACK_V1 = _manifest(
    "campaign_plan",
    OperationIntent.CAMPAIGN,
    ("campaign-goal", "audience", "campaign-window"),
    (
        _step(
            "campaign-strategy",
            "operation.campaign_plan",
            C.CAMPAIGN_PLAN,
            ("campaign-strategy",),
        ),
    ),
    (_requirement("campaign-strategy", DeliverableKind.PLAN),),
    frozenset({ProfileKind.CAMPAIGN, ProfileKind.AUDIENCE}),
)

CONTENT_CALENDAR_PACK_V1 = _manifest(
    "content_calendar",
    OperationIntent.PLAN,
    ("topic-scope", "calendar-window"),
    (
        _step(
            "content-calendar",
            "operation.content_create",
            C.CONTENT_CREATE,
            ("content-calendar",),
        ),
    ),
    (_requirement("content-calendar", DeliverableKind.PLAN),),
)

GROWTH_EXPERIMENT_PACK_V1 = _manifest(
    "growth_experiment",
    OperationIntent.OPTIMIZE,
    ("growth-goal", "funnel-stage", "experiment-window"),
    (
        _step(
            "growth-plan",
            "operation.user_growth_plan",
            C.USER_GROWTH_PLAN,
            ("experiment-backlog",),
        ),
    ),
    (_requirement("experiment-backlog", DeliverableKind.PLAN),),
)

OPERATION_REVIEW_PACK_V1 = _manifest(
    "operation_review",
    OperationIntent.REVIEW,
    ("review-window", "metric-definition"),
    (
        _step(
            "operation-review",
            "operation.analytics_review",
            C.ANALYTICS_REVIEW,
            ("review-report",),
        ),
    ),
    (_requirement("review-report", DeliverableKind.ANALYSIS),),
    frozenset({ProfileKind.METRIC}),
)


def build_s6_manifests() -> tuple[ScenarioPackManifest, ...]:
    """返回八个显式版本化场景包。"""

    return (
        INDUSTRY_DIGEST_PACK_V1,
        MULTI_PLATFORM_CONTENT_PACK_V1,
        BRAND_OPERATION_PLAN_PACK_V1,
        IP_OPERATION_PLAN_PACK_V1,
        CAMPAIGN_PLAN_PACK_V1,
        CONTENT_CALENDAR_PACK_V1,
        GROWTH_EXPERIMENT_PACK_V1,
        OPERATION_REVIEW_PACK_V1,
    )


__all__ = [
    "BRAND_OPERATION_PLAN_PACK_V1",
    "CAMPAIGN_PLAN_PACK_V1",
    "CONTENT_CALENDAR_PACK_V1",
    "GROWTH_EXPERIMENT_PACK_V1",
    "INDUSTRY_DIGEST_PACK_V1",
    "IP_OPERATION_PLAN_PACK_V1",
    "MULTI_PLATFORM_CONTENT_PACK_V1",
    "OPERATION_REVIEW_PACK_V1",
    "build_s6_manifests",
]
