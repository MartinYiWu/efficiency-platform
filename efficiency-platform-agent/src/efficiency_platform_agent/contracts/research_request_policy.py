"""研究请求中的数量、时间与来源约束值解析。"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow

_CHINA = ZoneInfo("Asia/Shanghai")
_COUNT = re.compile(r"(?<!\d)(\d{1,2})\s*条")
_ISO_DAY = re.compile(r"(?<!\d)(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?")
_ROLLING_DAYS = re.compile(r"(?:过去|最近|近)\s*(\d{1,3})\s*天")
_OFFICIAL_MARKERS = (
    "只接受官方",
    "仅接受官方",
    "必须来自官方",
    "一手官方",
    "官方博客",
    "论文主页",
    "官方release",
    "官方 release",
    "github官方",
    "github 官方",
)


def requested_source_count(text: str, *, default: int, maximum: int = 20) -> int:
    """提取用户明确要求的条目数；没有明确数量时保留调用方默认值。"""

    match = _COUNT.search(text)
    if match is None:
        return default
    return max(1, min(int(match.group(1)), maximum))


def has_explicit_source_count(text: str) -> bool:
    """判断条目数量是否由用户明确提出，而不是系统采集上限。"""

    return _COUNT.search(text) is not None


def has_explicit_time_window(text: str) -> bool:
    """判断用户是否明确给出日期或相对时间，而非仅要求“最新”。"""

    return bool(
        _ISO_DAY.search(text)
        or _ROLLING_DAYS.search(text)
        or any(marker in text for marker in ("今天", "昨天", "上周"))
    )


def official_sources_only(text: str) -> bool:
    """识别只允许一手/官方来源的语义约束。"""

    compact = " ".join(text.casefold().split())
    return any(marker in compact for marker in _OFFICIAL_MARKERS)


def resolve_research_window(
    text: str,
    *,
    now: datetime | None = None,
) -> ResolvedTimeWindow:
    """解析常用中文研究时间表达式，返回上海时区对应的 UTC 左闭右开窗口。"""

    anchor = (now or datetime.now(UTC)).astimezone(UTC)
    local_anchor = anchor.astimezone(_CHINA)
    local_midnight = local_anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    match = _ISO_DAY.search(text)
    precision: Literal["day", "week", "exact"] = "day"
    if match is not None:
        start_local = datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            tzinfo=_CHINA,
        )
        end_local = start_local + timedelta(days=1)
        original = match.group(0)
    elif "昨天" in text:
        start_local = local_midnight - timedelta(days=1)
        end_local = local_midnight
        original = "昨天"
    elif "今天" in text:
        start_local = local_midnight
        end_local = local_midnight + timedelta(days=1)
        original = "今天"
    elif "上周" in text:
        current_week = local_midnight - timedelta(days=local_midnight.weekday())
        start_local = current_week - timedelta(days=7)
        end_local = current_week
        original = "上周"
        precision = "week"
    elif (rolling := _ROLLING_DAYS.search(text)) is not None:
        days = max(1, min(int(rolling.group(1)), 365))
        start_local = local_anchor - timedelta(days=days)
        end_local = local_anchor
        original = rolling.group(0)
        precision = "exact"
    else:
        start_local = local_anchor - timedelta(days=7)
        end_local = local_anchor
        original = "最近7天（默认窗口）"
        precision = "exact"
    return ResolvedTimeWindow(
        start=start_local.astimezone(UTC),
        end=end_local.astimezone(UTC),
        timezone="Asia/Shanghai",
        precision=precision,
        original_text=original,
        anchor=anchor,
    )


def describe_research_constraints(
    text: str,
    *,
    requested_count: int,
    delivered_count: int,
    count_required: bool,
    now: datetime | None = None,
) -> str:
    """生成供下游模型消费的可信研究约束摘要。"""

    window = resolve_research_window(text, now=now)
    shortage = delivered_count < requested_count
    rules = [
        f"时间窗={window.original_text}",
        f"起点={window.start.isoformat()}",
        f"终点={window.end.isoformat()}（左闭右开）",
        f"有效来源数={delivered_count}",
    ]
    if has_explicit_time_window(text):
        rules.append(
            "用户已显式指定时间窗，任何默认窗口不适用且不得在输出中声称使用默认窗口"
        )
    if count_required:
        rules.insert(-1, f"目标条数={requested_count}")
    else:
        rules.insert(-1, f"条数策略=best_effort，上限={requested_count}")
    if count_required and shortage:
        rules.append("来源不足时必须明确说明，且不得扩大时间范围或编造来源")
    else:
        rules.append("不得扩大时间范围或编造来源")
    return "研究执行约束：" + "；".join(rules)


__all__ = [
    "describe_research_constraints",
    "has_explicit_source_count",
    "has_explicit_time_window",
    "official_sources_only",
    "requested_source_count",
    "resolve_research_window",
]
