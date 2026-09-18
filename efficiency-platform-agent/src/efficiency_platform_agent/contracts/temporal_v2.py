"""意图与研究共享的时间表达契约。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


type TemporalBasis = Literal["published_at", "updated_at", "event_at"]


class CalendarPeriodExpression(_FrozenContract):
    kind: Literal["calendar_period"] = "calendar_period"
    text: str = Field(min_length=1, max_length=256)
    period: Literal["day", "week", "month", "quarter", "year"]
    offset: StrictInt = Field(default=0, ge=-100, le=100)
    basis: TemporalBasis = "published_at"


class RollingDurationExpression(_FrozenContract):
    kind: Literal["rolling_duration"] = "rolling_duration"
    text: str = Field(min_length=1, max_length=256)
    amount: StrictInt = Field(ge=1, le=36_500)
    unit: Literal["hour", "day", "week", "month"]
    basis: TemporalBasis = "published_at"


class ExplicitRangeExpression(_FrozenContract):
    kind: Literal["explicit_range"] = "explicit_range"
    text: str = Field(min_length=1, max_length=256)
    start_text: str = Field(min_length=1, max_length=128)
    end_text: str = Field(min_length=1, max_length=128)
    basis: TemporalBasis = "published_at"


class BeforeAfterExpression(_FrozenContract):
    kind: Literal["before_after"] = "before_after"
    text: str = Field(min_length=1, max_length=256)
    relation: Literal["before", "after"]
    boundary_text: str = Field(min_length=1, max_length=128)
    basis: TemporalBasis = "published_at"


class UnspecifiedTemporalExpression(_FrozenContract):
    kind: Literal["unspecified"] = "unspecified"
    text: None = None
    basis: TemporalBasis = "published_at"


TemporalExpression = Annotated[
    CalendarPeriodExpression
    | RollingDurationExpression
    | ExplicitRangeExpression
    | BeforeAfterExpression
    | UnspecifiedTemporalExpression,
    Field(discriminator="kind"),
]


class ResolvedTimeWindow(_FrozenContract):
    schema_version: Literal["resolved-time-window/2"] = "resolved-time-window/2"
    start: datetime
    end: datetime
    timezone: str = Field(min_length=1, max_length=128)
    boundary: Literal["left_closed_right_open"] = "left_closed_right_open"
    precision: Literal["hour", "day", "week", "month", "exact"]
    original_text: str | None = Field(default=None, max_length=256)
    anchor: datetime
    basis: TemporalBasis = "published_at"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """时区必须是可解析的 IANA 标识。"""

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("TIMEZONE_INVALID") from exc
        return value

    @field_validator("start", "end", "anchor")
    @classmethod
    def validate_aware_utc(cls, value: datetime) -> datetime:
        """持久化时间仅接受明确的 UTC 时刻。"""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("TIME_NAIVE")
        if value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("TIME_NOT_UTC")
        return value

    @model_validator(mode="after")
    def validate_order(self) -> ResolvedTimeWindow:
        """时间窗采用左闭右开且必须具有正长度。"""

        if self.start >= self.end:
            raise ValueError("TIME_RANGE_INVALID")
        return self


__all__ = [
    "BeforeAfterExpression",
    "CalendarPeriodExpression",
    "ExplicitRangeExpression",
    "ResolvedTimeWindow",
    "RollingDurationExpression",
    "TemporalBasis",
    "TemporalExpression",
    "UnspecifiedTemporalExpression",
]
