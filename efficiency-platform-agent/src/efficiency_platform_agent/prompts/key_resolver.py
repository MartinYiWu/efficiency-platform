"""受控场景、阶段和平台到数据库 Prompt Key 的唯一映射。"""

from types import MappingProxyType

from efficiency_platform_agent.contracts.operation_intent import OperationScenario

_PROMPT_KEYS = MappingProxyType(
    {
        ("industry_digest", "compose", None): "industry_digest.compose",
        ("industry_digest", "repair", None): "industry_digest.repair",
        ("multi_platform_content", "draft", "wechat"): "content.wechat.draft",
        ("multi_platform_content", "repair", "wechat"): "content.wechat.repair",
        ("multi_platform_content", "draft", "xiaohongshu"): "content.xiaohongshu.draft",
        ("multi_platform_content", "repair", "xiaohongshu"): "content.xiaohongshu.repair",
        ("multi_platform_content", "draft", "toutiao"): "content.toutiao.draft",
        ("multi_platform_content", "repair", "toutiao"): "content.toutiao.repair",
        ("brand_operation_plan", "plan", None): "brand.plan",
        ("brand_operation_plan", "repair", None): "brand.repair",
        ("ip_operation_plan", "plan", None): "ip.plan",
        ("ip_operation_plan", "repair", None): "ip.repair",
        ("campaign_plan", "plan", None): "campaign.plan",
        ("campaign_plan", "repair", None): "campaign.repair",
        ("content_calendar", "plan", None): "calendar.plan",
        ("content_calendar", "repair", None): "calendar.repair",
        ("growth_experiment", "plan", None): "growth.plan",
        ("growth_experiment", "repair", None): "growth.repair",
        ("operation_review", "analyze", None): "review.analyze",
        ("operation_review", "repair", None): "review.repair",
    }
)


class PromptKeyResolver:
    @staticmethod
    def intent(*, repair: bool = False) -> str:
        return "intent.repair" if repair else "intent.plan"

    @staticmethod
    def research(stage: str) -> str:
        if stage not in {"plan", "relevance", "synthesize", "reflect", "repair"}:
            raise ValueError("PROMPT_STAGE_UNSUPPORTED")
        return f"research.{stage}"

    @staticmethod
    def scenario(
        scenario: OperationScenario, stage: str, *, platform: str | None = None
    ) -> str:
        try:
            return _PROMPT_KEYS[(scenario, stage, platform)]
        except KeyError as exc:
            raise ValueError("PROMPT_ROUTE_UNSUPPORTED") from exc

    @staticmethod
    def artifact(*, repair: bool = False) -> str:
        return "artifact.repair" if repair else "artifact.revise"


__all__ = ["PromptKeyResolver"]
