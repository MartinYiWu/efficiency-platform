"""确定性研究意图补丁测试。"""

import pytest

from efficiency_platform_agent.contracts.temporal_v2 import (
    CalendarPeriodExpression,
    RollingDurationExpression,
)
from efficiency_platform_agent.orchestration.intent_v2.deterministic import _temporal


@pytest.mark.parametrize(
    ("text", "amount", "unit"),
    (("近3天", 3, "day"), ("过去1天", 1, "day"), ("过去2周", 2, "week"), ("最近两周", 2, "week")),
)
def test_dynamic_duration_keeps_requested_amount(
    text: str, amount: int, unit: str
) -> None:
    result = _temporal(text)

    assert isinstance(result, RollingDurationExpression)
    assert result.amount == amount
    assert result.unit == unit


def test_last_week_is_previous_calendar_week() -> None:
    result = _temporal("上周")

    assert isinstance(result, CalendarPeriodExpression)
    assert result.period == "week"
    assert result.offset == -1
