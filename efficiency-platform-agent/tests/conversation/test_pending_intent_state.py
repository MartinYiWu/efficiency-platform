from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
from efficiency_platform_agent.contracts.intent import (
    IntentEnvelopeV1,
    IntentRequirementsV1,
)
from efficiency_platform_agent.conversation.service import (
    _merge_pending_intent,
    _operation_input_text,
    _research_time_window,
)


def _intent(task_type: str, goal: str, **requirements: object) -> IntentEnvelopeV1:
    return IntentEnvelopeV1(
        domain="测试",
        goal=goal,
        task_type=task_type,
        confidence=0.95,
        requirements=IntentRequirementsV1(**requirements),
    )


def test_date_only_reply_completes_pending_campaign_window() -> None:
    previous = _intent(
        "campaign_plan",
        "策划预算5000元、公司内部100人的AI工具推广活动",
        campaign_goal="推广AI工具",
        audience="公司内部100人",
    ).model_copy(
        update={"missing_fields": ["campaign_window"], "needs_clarification": True}
    )
    current = _intent("general_chat", "活动时间是2026年9月20日至9月27日")

    merged = _merge_pending_intent(previous, current)

    assert merged.task_type == "campaign_plan"
    assert merged.requirements.campaign_window == "活动时间是2026年9月20日至9月27日"
    assert merged.missing_fields == []
    assert merged.needs_clarification is False


def test_explicit_new_general_question_supersedes_stale_pending_intent() -> None:
    previous = _intent("campaign_plan", "策划活动").model_copy(
        update={"missing_fields": ["campaign_window"], "needs_clarification": True}
    )
    current = _intent("general_chat", "请用两句话解释RSS是什么")

    assert _merge_pending_intent(previous, current) is current


def test_operation_input_contains_resolved_structured_constraints() -> None:
    intent = _intent(
        "campaign_plan",
        "策划AI工具推广活动",
        campaign_goal="推广AI工具",
        audience="公司内部100人",
        campaign_window="2026年9月20日至9月27日",
    )

    value = _operation_input_text("时间补充完成", intent)

    assert "策划AI工具推广活动" in value
    assert "公司内部100人" in value
    assert "2026年9月20日至9月27日" in value


def test_explicit_message_day_overrides_model_default_latest_window() -> None:
    intent = _intent(
        "industry_digest",
        "收集 AI 新闻",
        topic="AI 新闻",
        time_window="最近7天（默认最新信息窗口）",
    )
    message = ConversationMessageV1(
        message="收集2026年9月16日的AI新闻",
        request_id="request-date",
        user_id="user-1",
    )

    assert _research_time_window(intent, message) == "2026年9月16日"
