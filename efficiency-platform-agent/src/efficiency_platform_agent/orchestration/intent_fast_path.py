"""对明确联网研究请求执行无外部 I/O 的确定性意图预判。"""

from __future__ import annotations

import re

from efficiency_platform_agent.contracts.intent import (
    IntentEnvelopeV1,
    IntentRequirementsV1,
)
from efficiency_platform_agent.conversation.context import ConversationContext

_PLATFORM_ALIASES: tuple[tuple[str, str], ...] = (
    ("微信公众号", "wechat_official_account"),
    ("公众号", "wechat_official_account"),
    ("wechat_official_account", "wechat_official_account"),
    ("小红书", "xiaohongshu"),
    ("xiaohongshu", "xiaohongshu"),
    ("今日头条", "toutiao"),
    ("头条", "toutiao"),
    ("toutiao", "toutiao"),
)
_RESEARCH_MARKERS = (
    "搜索",
    "搜一下",
    "查一下",
    "查找",
    "查询",
    "核实",
    "查证",
    "验证",
    "联网",
    "收集",
    "来源",
)
_NEGATED_RESEARCH_MARKERS = (
    "不需要联网",
    "无需联网",
    "不用联网",
    "不联网",
    "无需搜索",
    "不要联网",
)
_TIME_WINDOWS: tuple[tuple[str, str], ...] = (
    ("最近7天", "最近7天"),
    ("最近一周", "最近一周"),
    ("近7天", "近7天"),
    ("本周", "本周"),
    ("下周", "下周"),
    ("本月", "本月"),
    ("今天", "今天"),
    ("明天", "明天"),
)
_GENERIC_TOPICS = frozenset(
    {
        "动态",
        "最新动态",
        "热点",
        "最新热点",
        "新闻",
        "行业动态",
        "信息",
        "内容",
    }
)
_CONTENT_MARKERS = (
    "整理成",
    "生成",
    "编写",
    "撰写",
    "写一篇",
    "推文",
    "文章",
    "文案",
    "版本",
    "排版",
)
_FOLLOW_UP_MARKERS = ("上一版", "刚才", "前面", "原有", "保留")
_TOPIC_PREFIXES = (
    "收集",
    "搜索",
    "搜一下",
    "查一下",
    "查找",
    "查询",
    "核实",
    "查证",
    "验证",
    "获取",
    "整理",
    "生成",
    "编写",
    "撰写",
    "请",
    "帮我",
    "写一篇",
)
_TOPIC_SUFFIXES = (
    "三种版本",
    "多个版本",
    "多平台版本",
    "独立成品",
    "平台内容",
    "推文",
    "文章",
)


def _extract_platforms(text: str) -> tuple[str, ...]:
    """提取用户明确提到的平台，并按原文出现顺序去重。"""
    found: list[tuple[int, str]] = []
    for alias, canonical in _PLATFORM_ALIASES:
        for match in re.finditer(re.escape(alias), text, flags=re.IGNORECASE):
            found.append((match.start(), canonical))
    result: list[str] = []
    for _, canonical in sorted(found):
        if canonical not in result:
            result.append(canonical)
    return tuple(result)


def _extract_time_window(text: str) -> str | None:
    """从有限时间词表提取时间窗口，不猜测用户未表达的日期。"""
    for marker, value in _TIME_WINDOWS:
        if marker in text:
            return value
    return None


def _clean_topic(value: str) -> str | None:
    """清除受控动作词和平台格式词，保留用户原文中的主题。"""
    topic = value.strip(" ，。！？、；：:,.!?()（）\"'")
    # 连续动作词（例如“请搜索”）必须全部剥离，避免把指令词当成研究主题。
    changed = True
    while changed:
        changed = False
        for prefix in _TOPIC_PREFIXES:
            candidate = topic.removeprefix(prefix).strip()
            if candidate != topic:
                topic = candidate
                changed = True
                break
    for suffix in _TOPIC_SUFFIXES:
        topic = topic.removesuffix(suffix).strip()
    topic = re.sub(r"^为(.+?)(?:写|编写|撰写)$", r"\1", topic).strip()
    topic = re.sub(r"^(最新|近期|最近|下周|本周|本月|今天|明天)\s*", "", topic)
    topic = re.sub(r"(公众号|小红书|今日头条|头条|三种版本|多平台)\s*$", "", topic)
    topic = topic.strip("的 ")
    topic = topic.strip(" ，。！？、；：:,.!?()（）\"'")
    if (
        not topic
        or topic in _GENERIC_TOPICS
    ):
        return None
    return topic


def _extract_topic(text: str, context: ConversationContext) -> str | None:
    """只从当前消息或可见历史提取主题，不调用模型也不访问网络。"""
    current = text
    for marker, _ in _TIME_WINDOWS:
        current = current.replace(marker, " ")
    for alias, _ in _PLATFORM_ALIASES:
        current = re.sub(re.escape(alias), " ", current, flags=re.IGNORECASE)
    current = re.sub(r"(三种|多个|多平台)\s*版本", " ", current)
    current = re.sub(r"[，。；;、：:]+", "|", current)
    parts = [part for part in current.split("|") if part.strip()]
    for part in parts:
        cleaned = _clean_topic(part)
        if cleaned is not None and not any(
            marker in cleaned for marker in ("整理成", "生成", "版本")
        ):
            return cleaned

    # “给我来源”一类追问允许继承最近一条可见用户主题，但不编造新主题。
    if any(marker in text for marker in ("来源", "查一下", "搜索")):
        for turn in reversed(context.turns):
            if turn.role != "user" or turn.content.strip() == text.strip():
                continue
            inherited = _extract_topic(turn.content, ConversationContext())
            if inherited is not None:
                return inherited
    return None


def _previous_content_request(
    message: str, context: ConversationContext
) -> tuple[str, tuple[str, ...]] | None:
    """从可见历史中取得最近一次多平台内容请求的主题和平台。"""
    if not any(marker in message for marker in _FOLLOW_UP_MARKERS):
        return None
    for turn in reversed(context.turns):
        if turn.role != "user" or not turn.content.strip():
            continue
        platforms = _extract_platforms(turn.content)
        if not platforms or not any(
            marker in turn.content for marker in _CONTENT_MARKERS
        ):
            continue
        topic = _extract_topic(turn.content, ConversationContext())
        if topic is not None:
            return topic, platforms
    return None


def detect_fast_path_intent(
    text: str,
    context: ConversationContext,
) -> IntentEnvelopeV1 | None:
    """只对明确联网研究请求生成受控意图；普通或复杂请求返回 ``None``。"""
    if not isinstance(text, str) or not text.strip():
        return None
    if not isinstance(context, ConversationContext):
        raise TypeError("context必须是ConversationContext")

    message = text.strip()
    previous = _previous_content_request(message, context)
    if previous is not None and any(
        marker in message for marker in _CONTENT_MARKERS
    ):
        previous_topic, platforms = previous
        return IntentEnvelopeV1(
            domain="运营",
            goal=message,
            task_type="multi_platform_content",
            channels=list(platforms),
            time_range=None,
            needs_research=False,
            needs_multi_agent=True,
            missing_fields=[],
            needs_clarification=False,
            confidence=0.96,
            model_hint="fast",
            requirements=IntentRequirementsV1(
                topic=previous_topic,
                platforms=platforms,
            ),
        )
    network_disabled = any(
        marker in message for marker in _NEGATED_RESEARCH_MARKERS
    )
    platforms = _extract_platforms(message)
    is_content_request = bool(platforms) and any(
        marker in message for marker in _CONTENT_MARKERS
    )
    if (
        not network_disabled
        and not any(marker in message for marker in _RESEARCH_MARKERS)
        and not is_content_request
    ):
        return None

    time_window = _extract_time_window(message)
    topic: str | None = _extract_topic(message, context)
    if not is_content_request and topic and topic.replace(" ", "") == "AI行业动态":
        # 单独研究请求中的泛化主题仍需澄清；只有在明确要求成文时才视为可交付主题。
        topic = None
    if network_disabled and not is_content_request:
        return None
    task_type = "multi_platform_content" if is_content_request else "industry_digest"
    if task_type == "industry_digest" and time_window is None:
        time_window = "最近7天（默认最新信息窗口）"

    missing_fields: list[str] = []
    if topic is None:
        missing_fields.append("topic")
    if task_type == "multi_platform_content" and not platforms:
        missing_fields.append("platforms")
    requirements = IntentRequirementsV1(
        topic=topic,
        time_window=time_window,
        platforms=platforms,
    )
    return IntentEnvelopeV1(
        domain="运营",
        goal=message,
        task_type=task_type,
        channels=list(platforms),
        time_range=time_window,
        needs_research=(
            not network_disabled
            and (
                any(marker in message for marker in _RESEARCH_MARKERS)
                or time_window is not None
                or (
                    topic is not None
                    and any(
                        marker in topic for marker in ("行业", "动态", "热点", "新闻")
                    )
                )
            )
        ),
        needs_multi_agent=True,
        missing_fields=missing_fields,
        needs_clarification=bool(missing_fields),
        confidence=0.98 if not missing_fields else 0.90,
        model_hint="fast",
        requirements=requirements,
    )


__all__ = ["detect_fast_path_intent"]
