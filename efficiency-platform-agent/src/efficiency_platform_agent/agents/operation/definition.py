"""运营 Specialist 能力目录与显式注册定义唯一来源。"""

from enum import StrEnum

from efficiency_platform_agent.core.agent import AgentSpec, CapabilitySpec
from efficiency_platform_agent.core.enums import AgentKind, StrategyMode
from efficiency_platform_agent.core.run import ExecutionBudget


class OperationSpecialistCapabilityId(StrEnum):
    RESEARCH_INSIGHT = "operation.research.insight"
    QUALITY_REVIEW = "operation.quality.review"
    BRAND_STRATEGY = "operation.brand.strategy"
    IP_STRATEGY = "operation.ip.strategy"
    PRODUCT_PLAN = "operation.product.plan"
    CONTENT_CREATE = "operation.content.create"
    CHANNEL_CONTENT = "operation.channel.content"
    CAMPAIGN_PLAN = "operation.campaign.plan"
    USER_GROWTH_PLAN = "operation.user_growth.plan"
    COMMUNITY_PLAN = "operation.community.plan"
    ANALYTICS_REVIEW = "operation.analytics.review"


def operation_specialist_capability_ids() -> tuple[str, ...]:
    """返回稳定且无重复的能力标识。"""

    return tuple(item.value for item in OperationSpecialistCapabilityId)


def operation_capability_specs() -> tuple[CapabilitySpec, ...]:
    """返回与能力枚举一一对应的注册能力声明。"""

    return tuple(
        CapabilitySpec(
            capability_id=item.value,
            semantic_version="1.0.0",
            owner="operation-specialists",
            input_schema_version="operation-specialist-input/1",
            output_schema_version="operation-specialist-result/1",
            permissions=(
                frozenset({"synthetic.read"})
                if item is OperationSpecialistCapabilityId.RESEARCH_INSIGHT
                else frozenset()
            ),
        )
        for item in OperationSpecialistCapabilityId
    )


_AGENT_ROWS: tuple[
    tuple[
        str,
        OperationSpecialistCapabilityId,
        str,
        StrategyMode,
        str,
        frozenset[str],
        frozenset[str],
        str,
        ExecutionBudget,
    ],
    ...,
] = (
    (
        "operation.research.insight",
        OperationSpecialistCapabilityId.RESEARCH_INSIGHT,
        "operation.research",
        StrategyMode.WORKFLOW,
        "operation.research.insight/1",
        frozenset({"synthetic_research"}),
        frozenset({"synthetic.read"}),
        "operation-evidence-quality/1",
        # 联网研究包含服务端搜索和多轮来源整理，预算高于普通内容专家。
        ExecutionBudget(3, 1, 4_000, 8_000, 240_000, 0),
    ),
    (
        "operation.quality.review",
        OperationSpecialistCapabilityId.QUALITY_REVIEW,
        "operation.quality_review",
        StrategyMode.DIRECT,
        "operation.quality.review/1",
        frozenset(),
        frozenset(),
        "operation-quality-review/1",
        ExecutionBudget(2, 0, 6_000, 2_000, 30_000, 0),
    ),
    (
        "operation.brand.strategy",
        OperationSpecialistCapabilityId.BRAND_STRATEGY,
        "operation.brand_strategy",
        StrategyMode.DIRECT,
        "operation.brand.strategy/1",
        frozenset(),
        frozenset(),
        "operation-strategy-quality/1",
        ExecutionBudget(2, 0, 6_000, 3_000, 30_000, 0),
    ),
    (
        "operation.ip.strategy",
        OperationSpecialistCapabilityId.IP_STRATEGY,
        "operation.ip_strategy",
        StrategyMode.DIRECT,
        "operation.ip.strategy/1",
        frozenset(),
        frozenset(),
        "operation-strategy-quality/1",
        ExecutionBudget(2, 0, 6_000, 3_000, 30_000, 0),
    ),
    (
        "operation.product.plan",
        OperationSpecialistCapabilityId.PRODUCT_PLAN,
        "operation.product_plan",
        StrategyMode.DIRECT,
        "operation.product.plan/1",
        frozenset(),
        frozenset(),
        "operation-strategy-quality/1",
        ExecutionBudget(2, 0, 6_000, 3_000, 30_000, 0),
    ),
    (
        "operation.content.create",
        OperationSpecialistCapabilityId.CONTENT_CREATE,
        "operation.content_create",
        StrategyMode.DIRECT,
        "operation.content.create/1",
        frozenset(),
        frozenset(),
        "operation-content-quality/1",
        ExecutionBudget(2, 0, 6_000, 4_000, 30_000, 0),
    ),
    (
        "operation.channel.content",
        OperationSpecialistCapabilityId.CHANNEL_CONTENT,
        "operation.channel_content",
        StrategyMode.DIRECT,
        "operation.channel.content/1",
        frozenset(),
        frozenset(),
        "operation-channel-quality/1",
        # 多平台成品允许 120 秒，和 S6 场景步骤预算保持一致。
        # 多平台长文案需要容纳完整 JSON 与正文，避免达到旧上限后截断。
        ExecutionBudget(2, 0, 5_000, 8_000, 120_000, 0),
    ),
    (
        "operation.campaign.plan",
        OperationSpecialistCapabilityId.CAMPAIGN_PLAN,
        "operation.campaign_plan",
        StrategyMode.DIRECT,
        "operation.campaign.plan/1",
        frozenset(),
        frozenset(),
        "operation-strategy-quality/1",
        ExecutionBudget(2, 0, 7_000, 4_000, 30_000, 0),
    ),
    (
        "operation.user_growth.plan",
        OperationSpecialistCapabilityId.USER_GROWTH_PLAN,
        "operation.user_growth_plan",
        StrategyMode.DIRECT,
        "operation.user_growth.plan/1",
        frozenset(),
        frozenset(),
        "operation-strategy-quality/1",
        ExecutionBudget(2, 0, 6_000, 3_000, 30_000, 0),
    ),
    (
        "operation.community.plan",
        OperationSpecialistCapabilityId.COMMUNITY_PLAN,
        "operation.community_plan",
        StrategyMode.DIRECT,
        "operation.community.plan/1",
        frozenset(),
        frozenset(),
        "operation-strategy-quality/1",
        ExecutionBudget(2, 0, 6_000, 3_000, 30_000, 0),
    ),
    (
        "operation.analytics.review",
        OperationSpecialistCapabilityId.ANALYTICS_REVIEW,
        "operation.analytics_review",
        StrategyMode.DIRECT,
        "operation.analytics.review/1",
        frozenset(),
        frozenset(),
        "operation-analytics-quality/1",
        ExecutionBudget(2, 0, 5_000, 3_000, 30_000, 0),
    ),
)


def operation_agent_specs() -> tuple[AgentSpec, ...]:
    """返回 11 个唯一 Specialist 的完整静态 AgentSpec。"""

    return tuple(
        AgentSpec(
            agent_id=agent_id,
            semantic_version="1.0.0",
            owner="operation-specialists",
            kind=AgentKind.SPECIALIST,
            capability_ids=frozenset({capability.value}),
            supported_task_types=frozenset({task_type}),
            input_schema_version="operation-specialist-input/1",
            output_schema_version="operation-specialist-result/1",
            state_schema_version=f"{agent_id}-state/1",
            checkpoint_version=f"{agent_id}-checkpoint/1",
            allowed_strategies=frozenset({strategy}),
            prompt_bundle_id=prompt_id,
            allowed_tools=tools,
            knowledge_scopes=frozenset(),
            memory_policy_id="operation-specialist-memory/1",
            model_policy_id="s5-fake-model/1",
            quality_policy_id=quality_policy,
            permissions=permissions,
            budget=budget,
            termination_conditions=frozenset({"succeeded", "failed"}),
        )
        for agent_id, capability, task_type, strategy, prompt_id, tools, permissions, quality_policy, budget in _AGENT_ROWS
    )


def register_operation_specialists(registry: object, dependencies: object) -> None:
    """显式注册全部 Specialist；不扫描模块、不在导入时产生副作用。"""

    from efficiency_platform_agent.agents.operation.specialists.analytics import (
        AnalyticsReviewAgent,
    )
    from efficiency_platform_agent.agents.operation.specialists.brand import (
        BrandOperationAgent,
    )
    from efficiency_platform_agent.agents.operation.specialists.campaign import (
        CampaignOperationAgent,
    )
    from efficiency_platform_agent.agents.operation.specialists.channel import (
        ChannelContentAgent,
    )
    from efficiency_platform_agent.agents.operation.specialists.community import (
        CommunityAgent,
    )
    from efficiency_platform_agent.agents.operation.specialists.content import (
        ContentAgent,
    )
    from efficiency_platform_agent.agents.operation.specialists.ip import (
        IPOperationAgent,
    )
    from efficiency_platform_agent.agents.operation.specialists.product import (
        ProductOperationAgent,
    )
    from efficiency_platform_agent.agents.operation.specialists.quality import (
        QualityReviewAgent,
    )
    from efficiency_platform_agent.agents.operation.specialists.research import (
        ResearchInsightAgent,
    )
    from efficiency_platform_agent.agents.operation.specialists.user_growth import (
        UserGrowthAgent,
    )
    from efficiency_platform_agent.capabilities.research.contracts import (
        ResearchProviderPort,
    )

    register = getattr(registry, "register", None)
    if not callable(register):
        raise TypeError("registry必须提供register端口")
    provider = getattr(dependencies, "research_provider", None)
    if provider is None and isinstance(dependencies, dict):
        provider = dependencies.get("research_provider")
    reader = getattr(dependencies, "analytics_reader", None)
    if reader is None and isinstance(dependencies, dict):
        reader = dependencies.get("analytics_reader")
    if not isinstance(provider, ResearchProviderPort):
        raise TypeError("research_provider依赖无效")
    builders = (
        lambda: ResearchInsightAgent(provider),
        QualityReviewAgent,
        BrandOperationAgent,
        IPOperationAgent,
        ProductOperationAgent,
        ContentAgent,
        ChannelContentAgent,
        CampaignOperationAgent,
        UserGrowthAgent,
        CommunityAgent,
        lambda: AnalyticsReviewAgent(reader),
    )
    for spec, builder in zip(operation_agent_specs(), builders, strict=True):
        register(spec, builder)


__all__ = [
    "OperationSpecialistCapabilityId",
    "operation_agent_specs",
    "operation_capability_specs",
    "operation_specialist_capability_ids",
    "register_operation_specialists",
]
