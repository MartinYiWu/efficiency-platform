"""显式锚点驱动的确定性时间窗口解析。"""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dateparser  # type: ignore[import-untyped]

from efficiency_platform_agent.contracts.temporal_v2 import (
    BeforeAfterExpression,
    CalendarPeriodExpression,
    ExplicitRangeExpression,
    ResolvedTimeWindow,
    RollingDurationExpression,
    TemporalExpression,
    UnspecifiedTemporalExpression,
)

TemporalErrorCode = Literal["TIME_AMBIGUOUS", "TIME_INVALID"]

_VAGUE_QUANTITY = re.compile(r"(?:几|若干|数|some|few|several)", re.IGNORECASE)
_ARABIC_QUANTITY = re.compile(r"(?<!\d)(\d{1,5})(?!\d)")
_CHINESE_QUANTITY = re.compile(r"[零〇一二三四五六七八九十百两]+")
_YEAR_TOKEN = re.compile(r"(?<!\d)(?:1\d{3}|2\d{3})(?!\d)")
_DATE_ONLY = re.compile(
    r"^\s*(?:(?P<year>\d{4})\s*年\s*)?"
    r"(?:(?P<month>\d{1,2})\s*月\s*)?"
    r"(?P<day>\d{1,2})\s*(?P<day_suffix>[日号])?\s*$"
)
_ISO_DATE_ONLY = re.compile(
    r"^\s*(?P<year>\d{4})[-/.](?P<month>\d{1,2})[-/.](?P<day>\d{1,2})\s*$"
)
_TIME_ONLY = re.compile(
    r"^\s*(?P<hour>\d{1,2})(?:\s*[:点时]\s*)"
    r"(?P<minute>\d{1,2})?(?:\s*:\s*(?P<second>\d{1,2}))?\s*分?\s*$"
)
_YEAR_MONTH = re.compile(r"^\s*(?P<year>\d{4})\s*年\s*(?P<month>\d{1,2})\s*月\s*$")
_ISO_YEAR_MONTH = re.compile(r"^\s*(?P<year>\d{4})[-/.](?P<month>\d{1,2})\s*$")
_YEAR_QUARTER = re.compile(
    r"^\s*(?P<year>\d{4})\s*年\s*第?\s*(?P<quarter>[1-4一二三四])\s*季度\s*$"
)
_YEAR_ONLY = re.compile(r"^\s*(?P<year>\d{4})\s*年\s*$")

_CALENDAR_ALIASES: tuple[tuple[str, str, int], ...] = (
    ("yesterday", "day", -1),
    ("tomorrow", "day", 1),
    ("today", "day", 0),
    ("昨天", "day", -1),
    ("今天", "day", 0),
    ("今日", "day", 0),
    ("明天", "day", 1),
    ("last week", "week", -1),
    ("previous week", "week", -1),
    ("this week", "week", 0),
    ("next week", "week", 1),
    ("上星期", "week", -1),
    ("上周", "week", -1),
    ("本周", "week", 0),
    ("这周", "week", 0),
    ("下星期", "week", 1),
    ("下周", "week", 1),
    ("last month", "month", -1),
    ("this month", "month", 0),
    ("next month", "month", 1),
    ("上个月", "month", -1),
    ("上月", "month", -1),
    ("本月", "month", 0),
    ("这个月", "month", 0),
    ("下个月", "month", 1),
    ("下月", "month", 1),
    ("last quarter", "quarter", -1),
    ("this quarter", "quarter", 0),
    ("next quarter", "quarter", 1),
    ("上季度", "quarter", -1),
    ("本季度", "quarter", 0),
    ("下季度", "quarter", 1),
    ("last year", "year", -1),
    ("this year", "year", 0),
    ("next year", "year", 1),
    ("去年", "year", -1),
    ("今年", "year", 0),
    ("明年", "year", 1),
)

_UNIT_TOKENS: dict[str, tuple[str, ...]] = {
    "hour": ("小时", "hour", "hours", "hr", "hrs"),
    "day": ("天", "日", "day", "days"),
    "week": ("周", "星期", "week", "weeks"),
    "month": ("月", "month", "months"),
}


class TemporalResolutionError(ValueError):
    """只向调用方暴露稳定时间错误码。"""

    def __init__(self, code: TemporalErrorCode, reason: str) -> None:
        super().__init__(code)
        self.code = code
        self.reason = reason


class TemporalResolver:
    """把已结构化表达解析为冻结的 UTC 左闭右开窗口。"""

    def resolve(
        self,
        expression: TemporalExpression,
        anchor: datetime,
        timezone: str,
    ) -> ResolvedTimeWindow:
        zone, local_anchor = self._trusted_context(anchor, timezone)

        if isinstance(expression, UnspecifiedTemporalExpression):
            raise TemporalResolutionError(
                "TIME_AMBIGUOUS", "UNSPECIFIED_TIME_REQUIRES_POLICY"
            )
        precision: Literal["hour", "day", "week", "month", "exact"]
        if isinstance(expression, CalendarPeriodExpression):
            start, end, precision = self._resolve_calendar(
                expression, local_anchor, zone
            )
        elif isinstance(expression, RollingDurationExpression):
            start, end, precision = self._resolve_rolling(
                expression, local_anchor, zone
            )
        elif isinstance(expression, ExplicitRangeExpression):
            start, end, precision = self._resolve_explicit_range(
                expression, local_anchor, zone
            )
        elif isinstance(expression, BeforeAfterExpression):
            start, end, precision = self._resolve_before_after(
                expression, local_anchor, zone
            )
        else:  # pragma: no cover - discriminated union is closed by contract
            raise TemporalResolutionError("TIME_INVALID", "EXPRESSION_KIND_UNKNOWN")

        start_utc = start.astimezone(UTC)
        end_utc = end.astimezone(UTC)
        if start_utc >= end_utc:
            raise TemporalResolutionError("TIME_INVALID", "TIME_RANGE_INVALID")
        return ResolvedTimeWindow(
            start=start_utc,
            end=end_utc,
            timezone=timezone,
            precision=precision,
            original_text=expression.text,
            anchor=anchor.astimezone(UTC),
            basis=expression.basis,
        )

    @staticmethod
    def _trusted_context(
        anchor: datetime,
        timezone: str,
    ) -> tuple[ZoneInfo, datetime]:
        if anchor.tzinfo is None or anchor.utcoffset() is None:
            raise TemporalResolutionError("TIME_INVALID", "ANCHOR_TIME_NAIVE")
        try:
            zone = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise TemporalResolutionError("TIME_INVALID", "TIMEZONE_INVALID") from exc
        return zone, anchor.astimezone(zone)

    def _resolve_calendar(
        self,
        expression: CalendarPeriodExpression,
        anchor: datetime,
        zone: ZoneInfo,
    ) -> tuple[datetime, datetime, Literal["day", "week", "month"]]:
        try:
            start_date, end_date, precision = _calendar_dates(
                anchor.date(), expression.period, expression.offset
            )
            start = datetime.combine(start_date, time.min, zone)
            end = datetime.combine(end_date, time.min, zone)
        except (OverflowError, ValueError) as exc:
            raise TemporalResolutionError(
                "TIME_INVALID", "CALENDAR_RANGE_INVALID"
            ) from exc
        self._validate_calendar_text(expression, anchor, zone, start, end)
        return start, end, precision

    def _validate_calendar_text(
        self,
        expression: CalendarPeriodExpression,
        anchor: datetime,
        zone: ZoneInfo,
        start: datetime,
        end: datetime,
    ) -> None:
        normalized = " ".join(expression.text.casefold().split())
        if _VAGUE_QUANTITY.search(normalized):
            raise TemporalResolutionError("TIME_AMBIGUOUS", "VAGUE_CALENDAR_TEXT")
        alias_meanings = {
            (period, offset)
            for alias, period, offset in _CALENDAR_ALIASES
            if alias in normalized
        }
        if len(alias_meanings) > 1:
            raise TemporalResolutionError("TIME_AMBIGUOUS", "CALENDAR_TEXT_CONFLICT")
        if alias_meanings:
            period, offset = next(iter(alias_meanings))
            if expression.period != period or expression.offset != offset:
                raise TemporalResolutionError(
                    "TIME_AMBIGUOUS", "CALENDAR_TEXT_CONFLICT"
                )
            return
        parsed = _parse_with_dateparser(expression.text, anchor, zone)
        absolute_precision: str | None = None
        if parsed is None:
            absolute = _parse_absolute_calendar_reference(expression.text, zone)
            if absolute is not None:
                parsed, absolute_precision = absolute
        if parsed is None:
            raise TemporalResolutionError("TIME_AMBIGUOUS", "CALENDAR_TEXT_UNRESOLVED")
        if absolute_precision is not None and absolute_precision != expression.period:
            raise TemporalResolutionError(
                "TIME_AMBIGUOUS", "CALENDAR_PRECISION_CONFLICT"
            )
        if not start <= parsed < end:
            raise TemporalResolutionError("TIME_AMBIGUOUS", "CALENDAR_TEXT_CONFLICT")

    def _resolve_rolling(
        self,
        expression: RollingDurationExpression,
        anchor: datetime,
        zone: ZoneInfo,
    ) -> tuple[datetime, datetime, Literal["hour", "day", "week", "month"]]:
        self._validate_rolling_text(expression)
        end_utc = anchor.astimezone(UTC)
        if expression.unit == "hour":
            return (
                end_utc - timedelta(hours=expression.amount),
                end_utc,
                "hour",
            )
        if expression.unit == "day":
            return end_utc - timedelta(days=expression.amount), end_utc, "day"
        if expression.unit == "week":
            return end_utc - timedelta(weeks=expression.amount), end_utc, "week"
        try:
            year, month = _shift_year_month(
                anchor.year, anchor.month, -expression.amount
            )
            day = min(anchor.day, monthrange(year, month)[1])
            start = datetime(
                year,
                month,
                day,
                anchor.hour,
                anchor.minute,
                anchor.second,
                anchor.microsecond,
                tzinfo=zone,
            )
        except (OverflowError, ValueError) as exc:
            raise TemporalResolutionError(
                "TIME_INVALID", "ROLLING_MONTH_INVALID"
            ) from exc
        return start, anchor, "month"

    @staticmethod
    def _validate_rolling_text(expression: RollingDurationExpression) -> None:
        text = expression.text.casefold()
        if _VAGUE_QUANTITY.search(text):
            raise TemporalResolutionError("TIME_AMBIGUOUS", "VAGUE_DURATION")
        quantities = _extract_quantities(text)
        if not quantities:
            raise TemporalResolutionError(
                "TIME_AMBIGUOUS", "DURATION_QUANTITY_UNRESOLVED"
            )
        if len(quantities) != 1 or quantities[0] != expression.amount:
            raise TemporalResolutionError(
                "TIME_AMBIGUOUS", "DURATION_QUANTITY_CONFLICT"
            )
        mentioned_units = {
            unit
            for unit, tokens in _UNIT_TOKENS.items()
            if any(token in text for token in tokens)
        }
        if expression.unit not in mentioned_units or len(mentioned_units) != 1:
            raise TemporalResolutionError("TIME_AMBIGUOUS", "DURATION_UNIT_CONFLICT")

    def _resolve_explicit_range(
        self,
        expression: ExplicitRangeExpression,
        anchor: datetime,
        zone: ZoneInfo,
    ) -> tuple[datetime, datetime, Literal["day", "exact"]]:
        if (
            expression.start_text not in expression.text
            or expression.end_text not in expression.text
        ):
            raise TemporalResolutionError(
                "TIME_AMBIGUOUS", "RANGE_TEXT_COMPONENT_MISMATCH"
            )
        start = _parse_boundary(expression.start_text, anchor, zone)
        end = _parse_boundary(
            expression.end_text,
            anchor,
            zone,
            inherited_year=start.value.year,
            inherited_month=start.value.month,
            inherited_date=start.value.date(),
        )
        end_value = end.value + timedelta(days=1) if end.date_only else end.value
        if start.value >= end_value:
            if not start.has_year or not end.has_year:
                raise TemporalResolutionError(
                    "TIME_AMBIGUOUS", "YEARLESS_RANGE_CROSSES_YEAR"
                )
            raise TemporalResolutionError("TIME_INVALID", "TIME_RANGE_REVERSED")
        precision: Literal["day", "exact"] = (
            "day" if start.date_only and end.date_only else "exact"
        )
        return start.value, end_value, precision

    def _resolve_before_after(
        self,
        expression: BeforeAfterExpression,
        anchor: datetime,
        zone: ZoneInfo,
    ) -> tuple[datetime, datetime, Literal["day", "exact"]]:
        if expression.boundary_text not in expression.text:
            raise TemporalResolutionError(
                "TIME_AMBIGUOUS", "BOUNDARY_TEXT_COMPONENT_MISMATCH"
            )
        normalized = expression.text.casefold()
        before_markers = ("以前", "之前", "before")
        after_markers = ("以后", "之后", "after", "since")
        has_before = any(marker in normalized for marker in before_markers)
        has_after = any(marker in normalized for marker in after_markers)
        expected_present = has_before if expression.relation == "before" else has_after
        conflicting_present = (
            has_after if expression.relation == "before" else has_before
        )
        if not expected_present or conflicting_present:
            raise TemporalResolutionError(
                "TIME_AMBIGUOUS", "BOUNDARY_RELATION_CONFLICT"
            )
        boundary = _parse_boundary(expression.boundary_text, anchor, zone)
        if expression.relation == "before":
            raise TemporalResolutionError(
                "TIME_AMBIGUOUS", "UNBOUNDED_BEFORE_REQUIRES_START"
            )
        if boundary.value >= anchor and not boundary.has_year:
            raise TemporalResolutionError(
                "TIME_AMBIGUOUS", "YEARLESS_AFTER_BOUNDARY_IN_FUTURE"
            )
        if boundary.value >= anchor:
            raise TemporalResolutionError(
                "TIME_INVALID", "AFTER_BOUNDARY_NOT_BEFORE_ANCHOR"
            )
        precision: Literal["day", "exact"] = "day" if boundary.date_only else "exact"
        return boundary.value, anchor, precision


class _ParsedBoundary:
    def __init__(
        self,
        value: datetime,
        *,
        date_only: bool,
        has_year: bool,
    ) -> None:
        self.value = value
        self.date_only = date_only
        self.has_year = has_year


def _calendar_dates(
    anchor: date,
    period: Literal["day", "week", "month", "quarter", "year"],
    offset: int,
) -> tuple[date, date, Literal["day", "week", "month"]]:
    if period == "day":
        start = anchor + timedelta(days=offset)
        return start, start + timedelta(days=1), "day"
    if period == "week":
        start = anchor - timedelta(days=anchor.weekday()) + timedelta(weeks=offset)
        return start, start + timedelta(weeks=1), "week"
    months_per_period = 1
    base_month = anchor.month
    if period == "quarter":
        months_per_period = 3
        base_month = ((anchor.month - 1) // 3) * 3 + 1
    elif period == "year":
        months_per_period = 12
        base_month = 1
    start_year, start_month = _shift_year_month(
        anchor.year,
        base_month,
        offset * months_per_period,
    )
    end_year, end_month = _shift_year_month(
        start_year,
        start_month,
        months_per_period,
    )
    return date(start_year, start_month, 1), date(end_year, end_month, 1), "month"


def _shift_year_month(year: int, month: int, delta: int) -> tuple[int, int]:
    absolute = year * 12 + month - 1 + delta
    shifted_year, zero_based_month = divmod(absolute, 12)
    if shifted_year < 1 or shifted_year > 9999:
        raise ValueError("YEAR_OUT_OF_RANGE")
    return shifted_year, zero_based_month + 1


def _parse_with_dateparser(
    text: str,
    anchor: datetime,
    zone: ZoneInfo,
) -> datetime | None:
    parsed = dateparser.parse(
        text,
        languages=["zh", "en"],
        settings={
            "RELATIVE_BASE": anchor.replace(tzinfo=None),
            "TIMEZONE": zone.key,
            "TO_TIMEZONE": zone.key,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "past",
            "DATE_ORDER": "YMD",
            "STRICT_PARSING": True,
        },
    )
    if parsed is None:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def _parse_boundary(
    text: str,
    anchor: datetime,
    zone: ZoneInfo,
    *,
    inherited_year: int | None = None,
    inherited_month: int | None = None,
    inherited_date: date | None = None,
) -> _ParsedBoundary:
    stripped = text.strip()
    iso_match = _ISO_DATE_ONLY.fullmatch(stripped)
    chinese_match = _DATE_ONLY.fullmatch(stripped)
    match = iso_match or chinese_match
    if match is not None:
        if (
            chinese_match is not None
            and chinese_match.group("month") is None
            and chinese_match.group("day_suffix") is None
        ):
            raise TemporalResolutionError("TIME_AMBIGUOUS", "BARE_DAY_NUMBER_AMBIGUOUS")
        has_year = match.group("year") is not None
        year = int(match.group("year")) if has_year else inherited_year or anchor.year
        month_text = match.group("month")
        month = int(month_text) if month_text is not None else inherited_month
        if month is None:
            raise TemporalResolutionError("TIME_AMBIGUOUS", "BOUNDARY_MONTH_UNRESOLVED")
        try:
            value = datetime(
                year,
                month,
                int(match.group("day")),
                tzinfo=zone,
            )
        except ValueError as exc:
            raise TemporalResolutionError(
                "TIME_INVALID", "BOUNDARY_DATE_INVALID"
            ) from exc
        return _ParsedBoundary(value, date_only=True, has_year=has_year)

    time_match = _TIME_ONLY.fullmatch(stripped)
    if time_match is not None:
        if inherited_date is None:
            raise TemporalResolutionError(
                "TIME_AMBIGUOUS", "TIME_ONLY_BOUNDARY_HAS_NO_DATE"
            )
        try:
            value = datetime(
                inherited_date.year,
                inherited_date.month,
                inherited_date.day,
                int(time_match.group("hour")),
                int(time_match.group("minute") or 0),
                int(time_match.group("second") or 0),
                tzinfo=zone,
            )
        except ValueError as exc:
            raise TemporalResolutionError(
                "TIME_INVALID", "BOUNDARY_TIME_INVALID"
            ) from exc
        return _ParsedBoundary(value, date_only=False, has_year=False)

    parsed = _parse_with_dateparser(stripped, anchor, zone)
    if parsed is None:
        raise TemporalResolutionError("TIME_INVALID", "BOUNDARY_UNRESOLVED")
    has_year = _YEAR_TOKEN.search(stripped) is not None
    return _ParsedBoundary(parsed, date_only=False, has_year=has_year)


def _parse_absolute_calendar_reference(
    text: str,
    zone: ZoneInfo,
) -> tuple[datetime, str] | None:
    match = _YEAR_MONTH.fullmatch(text) or _ISO_YEAR_MONTH.fullmatch(text)
    if match is not None:
        try:
            return (
                datetime(
                    int(match.group("year")),
                    int(match.group("month")),
                    1,
                    tzinfo=zone,
                ),
                "month",
            )
        except ValueError as exc:
            raise TemporalResolutionError(
                "TIME_INVALID", "CALENDAR_TEXT_INVALID"
            ) from exc
    match = _YEAR_QUARTER.fullmatch(text)
    if match is not None:
        quarter_text = match.group("quarter")
        quarter = {"一": 1, "二": 2, "三": 3, "四": 4}.get(
            quarter_text,
            int(quarter_text) if quarter_text.isdigit() else 0,
        )
        return (
            datetime(
                int(match.group("year")),
                (quarter - 1) * 3 + 1,
                1,
                tzinfo=zone,
            ),
            "quarter",
        )
    match = _YEAR_ONLY.fullmatch(text)
    if match is not None:
        return datetime(int(match.group("year")), 1, 1, tzinfo=zone), "year"
    return None


def _extract_quantities(text: str) -> list[int]:
    quantities = [int(match.group(1)) for match in _ARABIC_QUANTITY.finditer(text)]
    for match in _CHINESE_QUANTITY.finditer(text):
        parsed = _parse_chinese_integer(match.group(0))
        if parsed is not None:
            quantities.append(parsed)
    return quantities


def _parse_chinese_integer(value: str) -> int | None:
    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if all(char in digits for char in value):
        result = 0
        for char in value:
            result = result * 10 + digits[char]
        return result
    total = 0
    current = 0
    for char in value:
        if char in digits:
            current = digits[char]
        elif char == "十":
            total += (current or 1) * 10
            current = 0
        elif char == "百":
            total += (current or 1) * 100
            current = 0
        else:
            return None
    return total + current


__all__ = ["TemporalResolutionError", "TemporalResolver"]
