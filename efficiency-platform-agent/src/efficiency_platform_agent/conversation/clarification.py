"""把结构化需求缺口转换为稳定的中文澄清问题。"""

from __future__ import annotations

from efficiency_platform_agent.contracts.intent import IntentEnvelopeV1

_QUESTIONS = {
    "product": "请补充本次要推广的产品或服务信息，包括名称和核心卖点。",
    "product_name": "请补充本次要推广的产品或服务名称。",
    "topic": "请补充本次运营内容的主题。",
    "platforms": "请确认需要覆盖的平台或渠道。",
    "channels": "请确认需要覆盖的平台或渠道。",
    "audience": "请补充目标受众及其主要特征。",
    "goal": "请明确本次运营任务希望达成的目标。",
    "budget": "请补充本次活动可使用的预算范围。",
    "time_range": "请补充本次任务的时间范围。",
    "time_window": "请补充行业简报需要覆盖的时间范围。",
    "planning_window": "请补充计划覆盖的时间范围。",
    "incubation_window": "请补充 IP 孵化计划覆盖的时间范围。",
    "campaign_goal": "请明确本次活动希望达成的目标。",
    "campaign_window": "请补充活动开始和结束时间。",
    "topic_scope": "请补充内容日历需要覆盖的主题范围。",
    "calendar_window": "请补充内容日历需要覆盖的日期范围。",
    "growth_goal": "请明确本次增长实验希望达成的目标。",
    "funnel_stage": "请确认本次增长实验针对的漏斗阶段。",
    "experiment_window": "请补充增长实验的开始和结束时间。",
    "review_window": "请补充本次运营复盘覆盖的时间范围。",
    "brand": "请补充品牌名称、定位和已有素材。",
    "ip": "请补充需要运营的 IP 及其当前定位。",
    "metric_definition": "请补充本次复盘使用的指标口径。",
    "data_file": "请提供本次复盘所需的数据文件。",
}


class ClarificationManager:
    """每轮只询问一个最前置缺口，避免一次抛出过多问题。"""

    def __init__(self, *, confidence_threshold: float = 0.65) -> None:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold必须在0到1之间")
        self.confidence_threshold = confidence_threshold

    def next_question(self, intent: IntentEnvelopeV1) -> str | None:
        """返回下一条安全问题；需求完整且置信度足够时返回空。"""
        if not isinstance(intent, IntentEnvelopeV1):
            raise TypeError("intent必须是IntentEnvelopeV1")
        if intent.missing_fields:
            field = intent.missing_fields[0].strip().lower().replace("-", "_")
            return _QUESTIONS.get(field, "请补充任务中缺少的关键信息，以便继续处理。")
        if intent.needs_clarification or intent.confidence < self.confidence_threshold:
            return "请再具体说明本次运营目标、对象和期望交付物。"
        return None


__all__ = ["ClarificationManager"]
