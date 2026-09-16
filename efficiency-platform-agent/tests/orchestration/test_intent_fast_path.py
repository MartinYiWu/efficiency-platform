"""联网研究快速意图预判的单元测试。"""

from efficiency_platform_agent.conversation.context import (
    ConversationContext,
    ConversationTurn,
)
from efficiency_platform_agent.orchestration.intent_fast_path import (
    detect_fast_path_intent,
)


def test_detects_research_and_multi_platform_request_without_model() -> None:
    intent = detect_fast_path_intent(
        "收集下周 AI 行业热点，整理成公众号、小红书和头条三种版本",
        ConversationContext(),
    )

    assert intent is not None
    assert intent.needs_research is True
    assert intent.needs_multi_agent is True
    assert intent.task_type == "multi_platform_content"
    assert tuple(intent.requirements.platforms) == (
        "wechat_official_account",
        "xiaohongshu",
        "toutiao",
    )
    assert intent.requirements.time_window == "下周"
    assert intent.requirements.topic == "AI 行业热点"
    assert intent.missing_fields == []


def test_detects_today_industry_article_as_researched_wechat_content() -> None:
    intent = detect_fast_path_intent(
        "帮我写一篇今天的AI行业动态的公众号推文",
        ConversationContext(),
    )

    assert intent is not None
    assert intent.task_type == "multi_platform_content"
    assert intent.needs_research is True
    assert intent.needs_multi_agent is True
    assert tuple(intent.requirements.platforms) == ("wechat_official_account",)
    assert intent.requirements.topic == "AI行业动态"
    assert intent.requirements.time_window == "今天"
    assert intent.missing_fields == []


def test_returns_none_for_chat_and_non_research_complex_request() -> None:
    assert detect_fast_path_intent("你是谁", ConversationContext()) is None
    assert (
        detect_fast_path_intent("制定品牌发布计划", ConversationContext()) is None
    )


def test_marks_missing_topic_for_research_request_without_inventing_topic() -> None:
    intent = detect_fast_path_intent(
        "搜索最新 AI 行业动态", ConversationContext()
    )

    assert intent is not None
    assert intent.task_type == "industry_digest"
    assert intent.needs_research is True
    assert intent.needs_multi_agent is True
    assert intent.requirements.topic is None
    assert intent.missing_fields == ["topic"]
    assert intent.needs_clarification is True


def test_negative_network_constraint_keeps_content_on_non_research_fast_path() -> None:
    """用户明确要求不联网时，仍可直接进入多平台内容编排。"""
    intent = detect_fast_path_intent(
        "请为新品写公众号、小红书和头条三种独立版本的发布文案，不需要联网",
        ConversationContext(),
    )

    assert intent is not None
    assert intent.task_type == "multi_platform_content"
    assert intent.needs_research is False
    assert intent.needs_multi_agent is True


def test_detects_content_revision_follow_up_from_visible_conversation_context() -> None:
    """上一轮已有多平台文案时，修改请求应复用平台与主题而非重新追问。"""
    context = ConversationContext()
    context.append(
        ConversationTurn(
            "user",
            "请为新品写公众号、小红书和头条三种独立版本的发布文案，不需要联网",
        )
    )
    context.append(ConversationTurn("assistant", "已生成三种平台版本。"))

    intent = detect_fast_path_intent(
        "把上一版文案改得更专业一些，并保留原有的三个重点。", context
    )

    assert intent is not None
    assert intent.task_type == "multi_platform_content"
    assert intent.needs_research is False
    assert tuple(intent.requirements.platforms) == (
        "wechat_official_account",
        "xiaohongshu",
        "toutiao",
    )
    assert intent.requirements.topic == "新品"
    assert intent.needs_clarification is False
