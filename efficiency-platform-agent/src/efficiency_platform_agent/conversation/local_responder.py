"""基础会话的确定性本地快速响应。"""

from __future__ import annotations

import re

_NORMALIZATION_PATTERN = re.compile(r"[\s，。！？、；：,.!?;:]+")
_GREETING_PATTERN = re.compile(r"(?:你好|嗨|哈喽|在吗|在不在)")
_IDENTITY_QUESTIONS = frozenset({"你是谁", "介绍一下自己", "自我介绍"})
_CAPABILITY_QUESTIONS = frozenset(
    {
        "你能做什么",
        "你能干什么",
        "你可以做什么",
        "你会做什么",
        "你会哪些",
        "可以帮我做什么",
        "能提供什么帮助",
        "有什么能力",
        "有哪些能力",
        "怎么使用",
        "如何使用",
    }
)
_THANKS_OR_FAREWELLS = frozenset({"谢谢", "感谢", "谢啦", "多谢", "再见", "拜拜"})

_IDENTITY_RESPONSE = "我是你的 AI 内容运营助手，可以协助完成内容与运营相关工作。"
_GREETING_RESPONSE = "你好，我是你的 AI 内容运营助手。"
_CAPABILITY_RESPONSE = (
    "我可以协助公开资料整理、内容策划、品牌/IP、活动方案、渠道文案和运营复盘；"
    "按需提供来源，方便你进一步核验和使用。"
)
_THANKS_RESPONSE = "不客气，随时告诉我你需要什么帮助。"


class LocalConversationResponder:
    """只为低歧义基础会话返回稳定中文正文。"""

    def respond(self, text: str) -> str | None:
        """命中稳定基础会话时返回正文，否则返回 None。"""
        normalized = _NORMALIZATION_PATTERN.sub("", text).strip()
        if normalized in _IDENTITY_QUESTIONS:
            return _IDENTITY_RESPONSE
        if _GREETING_PATTERN.fullmatch(normalized):
            return _GREETING_RESPONSE
        if normalized in _CAPABILITY_QUESTIONS:
            return _CAPABILITY_RESPONSE
        if normalized in _THANKS_OR_FAREWELLS:
            return _THANKS_RESPONSE
        return None


__all__ = ["LocalConversationResponder"]
