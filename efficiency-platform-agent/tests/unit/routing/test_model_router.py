"""模型策略路由的 RED/GREEN 契约测试。"""

from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.model import ModelDemand, ModelTier
from efficiency_platform_agent.routing.model_router import ModelPolicyRouter


def budget() -> RemainingBudget:
    """构造可用的合成剩余额度。"""
    return RemainingBudget(10, 10, 100, 100, 100, 1000)


def demand(tier: ModelTier = ModelTier.STRONG) -> ModelDemand:
    """构造强能力且需要结构化输出的需求。"""
    return ModelDemand("s2.model/1", tier, True, True, 10, 20)


def candidate_ids(
    router: ModelPolicyRouter, requested: ModelTier = ModelTier.STRONG
) -> list[str]:
    """返回候选 ID，便于验证稳定排序与过滤。"""
    return [
        item.candidate_id
        for item in router.candidates(
            demand(requested),
            remaining_budget=budget(),
            unavailable_candidate_ids=frozenset(),
        )
    ]


def test_strong_request_orders_strong_then_finite_degradation() -> None:
    """强需求只能按 strong、balanced、fast 向下有限降级。"""
    assert candidate_ids(ModelPolicyRouter()) == [
        "fake_strong",
        "fake_balanced",
        "fake_fast",
    ]


def test_hard_capability_budget_disabled_and_unhealthy_candidates_are_skipped() -> None:
    """硬能力、上下文、额度、禁用和不健康候选均不得进入尝试。"""
    router = ModelPolicyRouter(unavailable_candidate_ids=frozenset({"fake_balanced"}))
    demand_value = ModelDemand("s2.model/1", ModelTier.STRONG, True, True, 90, 20)
    result = router.candidates(
        demand_value,
        remaining_budget=RemainingBudget(10, 10, 50, 100, 100, 1000),
        unavailable_candidate_ids=frozenset({"fake_strong"}),
    )
    assert result == ()
