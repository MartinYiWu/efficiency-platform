"""基础会话本地快速响应的离线测试。"""

from __future__ import annotations

import pytest

from efficiency_platform_agent.conversation.local_responder import (
    LocalConversationResponder,
)


@pytest.mark.parametrize(
    ("message", "expected_fragment"),
    (
        ("你是谁？", "AI 内容运营助手"),
        ("你好", "你好"),
        ("你能做什么", "内容策划"),
        ("谢谢", "不客气"),
    ),
)
def test_stable_basic_conversations_return_controlled_response(
    message: str, expected_fragment: str
) -> None:
    responder = LocalConversationResponder()

    result = responder.respond(message)

    assert result is not None
    assert expected_fragment in result


def test_operation_request_is_not_consumed_by_local_responder() -> None:
    responder = LocalConversationResponder()

    assert responder.respond("帮我策划一次新品品牌活动") is None


def test_greeting_with_operation_request_is_not_consumed_by_local_responder() -> None:
    responder = LocalConversationResponder()

    assert responder.respond("你好，帮我策划新品活动") is None


@pytest.mark.parametrize(
    "message",
    ("你会哪些", "可以帮我做什么", "能提供什么帮助", "有什么能力"),
)
def test_capability_synonyms_return_product_capability_response(message: str) -> None:
    responder = LocalConversationResponder()

    result = responder.respond(message)

    assert result is not None
    for expected_fragment in (
        "公开资料整理",
        "内容策划",
        "品牌/IP",
        "活动",
        "渠道文案",
        "运营复盘",
        "来源",
    ):
        assert expected_fragment in result
