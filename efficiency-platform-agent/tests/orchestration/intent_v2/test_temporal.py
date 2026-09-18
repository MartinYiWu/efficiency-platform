"""I03 确定性时间解析的行为测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.temporal_v2 import (
    BeforeAfterExpression,
    CalendarPeriodExpression,
    ExplicitRangeExpression,
    ResolvedTimeWindow,
    RollingDurationExpression,
    UnspecifiedTemporalExpression,
)
from efficiency_platform_agent.orchestration.intent_v2.temporal import (
    TemporalResolutionError,
    TemporalResolver,
)

FIXED_ANCHOR = datetime.fromisoformat("2026-09-16T09:41:00+08:00")


def test_yesterday_is_calendar_day_not_rolling_24_hours() -> None:
    result = TemporalResolver().resolve(
        CalendarPeriodExpression(
            text="昨天",
            period="day",
            offset=-1,
            basis="published_at",
        ),
        FIXED_ANCHOR,
        "Asia/Shanghai",
    )

    assert result.start.isoformat() == "2026-09-14T16:00:00+00:00"
    assert result.end.isoformat() == "2026-09-15T16:00:00+00:00"
    assert result.anchor == FIXED_ANCHOR.astimezone(UTC)
    assert result.basis == "published_at"
    assert result.precision == "day"


def test_recent_24_hours_is_rolling_duration() -> None:
    result = TemporalResolver().resolve(
        RollingDurationExpression(
            text="最近24小时",
            amount=24,
            unit="hour",
            basis="updated_at",
        ),
        FIXED_ANCHOR,
        "Asia/Shanghai",
    )

    assert result.start.isoformat() == "2026-09-15T01:41:00+00:00"
    assert result.end.isoformat() == "2026-09-16T01:41:00+00:00"
    assert result.basis == "updated_at"
    assert result.precision == "hour"


def test_last_week_uses_monday_boundaries() -> None:
    result = TemporalResolver().resolve(
        CalendarPeriodExpression(text="上周", period="week", offset=-1),
        FIXED_ANCHOR,
        "Asia/Shanghai",
    )

    assert result.start.isoformat() == "2026-09-06T16:00:00+00:00"
    assert result.end.isoformat() == "2026-09-13T16:00:00+00:00"
    assert result.precision == "week"


def test_absolute_calendar_month_is_checked_against_structured_period() -> None:
    result = TemporalResolver().resolve(
        CalendarPeriodExpression(text="2026年9月", period="month", offset=0),
        FIXED_ANCHOR,
        "Asia/Shanghai",
    )

    assert result.start.isoformat() == "2026-08-31T16:00:00+00:00"
    assert result.end.isoformat() == "2026-09-30T16:00:00+00:00"


def test_natural_date_range_includes_entire_end_day() -> None:
    result = TemporalResolver().resolve(
        ExplicitRangeExpression(
            text="9月10日到12日",
            start_text="9月10日",
            end_text="12日",
            basis="event_at",
        ),
        FIXED_ANCHOR,
        "Asia/Shanghai",
    )

    assert result.start.isoformat() == "2026-09-09T16:00:00+00:00"
    assert result.end.isoformat() == "2026-09-12T16:00:00+00:00"
    assert result.basis == "event_at"
    assert result.precision == "day"


def test_structured_calendar_expression_conflicting_with_text_is_ambiguous() -> None:
    with pytest.raises(TemporalResolutionError) as caught:
        TemporalResolver().resolve(
            CalendarPeriodExpression(text="今天", period="day", offset=-1),
            FIXED_ANCHOR,
            "Asia/Shanghai",
        )

    assert caught.value.code == "TIME_AMBIGUOUS"


def test_multiple_conflicting_calendar_aliases_are_ambiguous() -> None:
    with pytest.raises(TemporalResolutionError) as caught:
        TemporalResolver().resolve(
            CalendarPeriodExpression(
                text="不是昨天，是今天",
                period="day",
                offset=-1,
            ),
            FIXED_ANCHOR,
            "Asia/Shanghai",
        )

    assert caught.value.code == "TIME_AMBIGUOUS"


def test_vague_recent_days_is_not_silently_defaulted_to_seven_days() -> None:
    with pytest.raises(TemporalResolutionError) as caught:
        TemporalResolver().resolve(
            RollingDurationExpression(text="最近几天", amount=7, unit="day"),
            FIXED_ANCHOR,
            "Asia/Shanghai",
        )

    assert caught.value.code == "TIME_AMBIGUOUS"


def test_multiple_conflicting_duration_quantities_are_ambiguous() -> None:
    with pytest.raises(TemporalResolutionError) as caught:
        TemporalResolver().resolve(
            RollingDurationExpression(
                text="最近24小时，不是48小时",
                amount=24,
                unit="hour",
            ),
            FIXED_ANCHOR,
            "Asia/Shanghai",
        )

    assert caught.value.code == "TIME_AMBIGUOUS"


def test_unspecified_expression_requires_policy_or_clarification() -> None:
    with pytest.raises(TemporalResolutionError) as caught:
        TemporalResolver().resolve(
            UnspecifiedTemporalExpression(),
            FIXED_ANCHOR,
            "Asia/Shanghai",
        )

    assert caught.value.code == "TIME_AMBIGUOUS"


@pytest.mark.parametrize(
    ("anchor", "expected_start", "expected_end", "hours"),
    [
        (
            datetime(2026, 3, 9, 12, tzinfo=ZoneInfo("America/New_York")),
            "2026-03-08T05:00:00+00:00",
            "2026-03-09T04:00:00+00:00",
            23,
        ),
        (
            datetime(2026, 11, 2, 12, tzinfo=ZoneInfo("America/New_York")),
            "2026-11-01T04:00:00+00:00",
            "2026-11-02T05:00:00+00:00",
            25,
        ),
    ],
)
def test_calendar_day_honors_dst_23_and_25_hour_days(
    anchor: datetime,
    expected_start: str,
    expected_end: str,
    hours: int,
) -> None:
    result = TemporalResolver().resolve(
        CalendarPeriodExpression(text="yesterday", period="day", offset=-1),
        anchor,
        "America/New_York",
    )

    assert result.start.isoformat() == expected_start
    assert result.end.isoformat() == expected_end
    assert (result.end - result.start).total_seconds() == hours * 3600


def test_previous_day_includes_leap_day() -> None:
    result = TemporalResolver().resolve(
        CalendarPeriodExpression(text="昨天", period="day", offset=-1),
        datetime.fromisoformat("2024-03-01T08:00:00+08:00"),
        "Asia/Shanghai",
    )

    assert result.start.isoformat() == "2024-02-28T16:00:00+00:00"
    assert result.end.isoformat() == "2024-02-29T16:00:00+00:00"


def test_explicit_full_year_range_can_cross_year() -> None:
    result = TemporalResolver().resolve(
        ExplicitRangeExpression(
            text="2025年12月31日到2026年1月2日",
            start_text="2025年12月31日",
            end_text="2026年1月2日",
        ),
        FIXED_ANCHOR,
        "Asia/Shanghai",
    )

    assert result.start.isoformat() == "2025-12-30T16:00:00+00:00"
    assert result.end.isoformat() == "2026-01-02T16:00:00+00:00"


def test_yearless_range_that_would_cross_year_is_ambiguous() -> None:
    with pytest.raises(TemporalResolutionError) as caught:
        TemporalResolver().resolve(
            ExplicitRangeExpression(
                text="12月31日到1月2日",
                start_text="12月31日",
                end_text="1月2日",
            ),
            FIXED_ANCHOR,
            "Asia/Shanghai",
        )

    assert caught.value.code == "TIME_AMBIGUOUS"


def test_partially_yearless_cross_year_range_is_ambiguous() -> None:
    with pytest.raises(TemporalResolutionError) as caught:
        TemporalResolver().resolve(
            ExplicitRangeExpression(
                text="2025年12月31日到1月2日",
                start_text="2025年12月31日",
                end_text="1月2日",
            ),
            FIXED_ANCHOR,
            "Asia/Shanghai",
        )

    assert caught.value.code == "TIME_AMBIGUOUS"


def test_invalid_calendar_date_is_invalid() -> None:
    with pytest.raises(TemporalResolutionError) as caught:
        TemporalResolver().resolve(
            ExplicitRangeExpression(
                text="2025年2月29日到3月1日",
                start_text="2025年2月29日",
                end_text="3月1日",
            ),
            FIXED_ANCHOR,
            "Asia/Shanghai",
        )

    assert caught.value.code == "TIME_INVALID"


def test_reverse_explicit_range_is_invalid_when_years_are_explicit() -> None:
    with pytest.raises(TemporalResolutionError) as caught:
        TemporalResolver().resolve(
            ExplicitRangeExpression(
                text="2026年9月12日到2026年9月10日",
                start_text="2026年9月12日",
                end_text="2026年9月10日",
            ),
            FIXED_ANCHOR,
            "Asia/Shanghai",
        )

    assert caught.value.code == "TIME_INVALID"


def test_exact_range_inherits_start_date_for_time_only_end() -> None:
    result = TemporalResolver().resolve(
        ExplicitRangeExpression(
            text="2026年9月10日 10:00到12:00",
            start_text="2026年9月10日 10:00",
            end_text="12:00",
        ),
        FIXED_ANCHOR,
        "Asia/Shanghai",
    )

    assert result.start.isoformat() == "2026-09-10T02:00:00+00:00"
    assert result.end.isoformat() == "2026-09-10T04:00:00+00:00"
    assert result.precision == "exact"


def test_bare_day_number_without_date_marker_is_ambiguous() -> None:
    with pytest.raises(TemporalResolutionError) as caught:
        TemporalResolver().resolve(
            ExplicitRangeExpression(
                text="9月10日到12",
                start_text="9月10日",
                end_text="12",
            ),
            FIXED_ANCHOR,
            "Asia/Shanghai",
        )

    assert caught.value.code == "TIME_AMBIGUOUS"


@pytest.mark.parametrize(
    ("anchor", "timezone"),
    [
        (datetime.fromisoformat("2026-09-16T09:41:00"), "Asia/Shanghai"),
        (FIXED_ANCHOR, "Mars/Olympus_Mons"),
    ],
)
def test_invalid_anchor_or_timezone_is_invalid(
    anchor: datetime,
    timezone: str,
) -> None:
    with pytest.raises(TemporalResolutionError) as caught:
        TemporalResolver().resolve(
            CalendarPeriodExpression(text="昨天", period="day", offset=-1),
            anchor,
            timezone,
        )

    assert caught.value.code == "TIME_INVALID"


def test_midnight_anchor_does_not_drift_to_system_time() -> None:
    result = TemporalResolver().resolve(
        CalendarPeriodExpression(text="昨天", period="day", offset=-1),
        datetime.fromisoformat("2026-09-16T00:00:00+08:00"),
        "Asia/Shanghai",
    )

    assert result.start.isoformat() == "2026-09-14T16:00:00+00:00"
    assert result.end.isoformat() == "2026-09-15T16:00:00+00:00"


def test_after_boundary_is_bounded_by_supplied_anchor() -> None:
    result = TemporalResolver().resolve(
        BeforeAfterExpression(
            text="2026年9月10日以后",
            relation="after",
            boundary_text="2026年9月10日",
        ),
        FIXED_ANCHOR,
        "Asia/Shanghai",
    )

    assert result.start.isoformat() == "2026-09-09T16:00:00+00:00"
    assert result.end == FIXED_ANCHOR.astimezone(UTC)


def test_yearless_future_after_boundary_is_ambiguous() -> None:
    with pytest.raises(TemporalResolutionError) as caught:
        TemporalResolver().resolve(
            BeforeAfterExpression(
                text="12月1日以后",
                relation="after",
                boundary_text="12月1日",
            ),
            FIXED_ANCHOR,
            "Asia/Shanghai",
        )

    assert caught.value.code == "TIME_AMBIGUOUS"


def test_relation_conflicting_with_original_text_is_ambiguous() -> None:
    with pytest.raises(TemporalResolutionError) as caught:
        TemporalResolver().resolve(
            BeforeAfterExpression(
                text="2026年9月10日以前",
                relation="after",
                boundary_text="2026年9月10日",
            ),
            FIXED_ANCHOR,
            "Asia/Shanghai",
        )

    assert caught.value.code == "TIME_AMBIGUOUS"


def test_unbounded_before_expression_requires_clarification() -> None:
    with pytest.raises(TemporalResolutionError) as caught:
        TemporalResolver().resolve(
            BeforeAfterExpression(
                text="2026年9月10日以前",
                relation="before",
                boundary_text="2026年9月10日",
            ),
            FIXED_ANCHOR,
            "Asia/Shanghai",
        )

    assert caught.value.code == "TIME_AMBIGUOUS"


def test_basis_survives_resolved_window_round_trip_and_is_closed() -> None:
    resolved = TemporalResolver().resolve(
        RollingDurationExpression(
            text="最近1天",
            amount=1,
            unit="day",
            basis="event_at",
        ),
        FIXED_ANCHOR,
        "Asia/Shanghai",
    )

    assert ResolvedTimeWindow.model_validate(resolved.model_dump()).basis == "event_at"
    with pytest.raises(ValidationError):
        RollingDurationExpression(
            text="最近1天",
            amount=1,
            unit="day",
            basis="retrieved_at",  # type: ignore[arg-type]
        )
