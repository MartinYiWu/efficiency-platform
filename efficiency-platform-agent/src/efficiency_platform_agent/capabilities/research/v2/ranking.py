"""不混加原始平台指标的可解释事件排序。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.contracts.research_evidence_v2 import EventClusterV2

RankingMode = Literal["importance", "heat", "recency"]
ImportanceLevel = Literal["critical", "high", "medium", "low"]
HeatMetric = Literal["score", "rank", "comments"]
_IMPORTANCE_SCORE: dict[ImportanceLevel, float] = {
    "critical": 4.0,
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EventRankingObservationV2(_FrozenContract):
    event_id: str = Field(min_length=1, max_length=128)
    observation_type: Literal["importance", "heat"]
    observed_at: datetime
    importance_level: ImportanceLevel | None = None
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)
    snapshot_id: str | None = Field(default=None, min_length=1, max_length=128)
    platform_id: str | None = Field(default=None, min_length=1, max_length=128)
    metric: HeatMetric | None = None
    metric_value: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_shape(self) -> EventRankingObservationV2:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("RANKING_OBSERVATION_TIME_NAIVE")
        if self.observation_type == "importance":
            if (
                self.importance_level is None
                or not self.reason_codes
                or self.platform_id is not None
                or self.snapshot_id is not None
                or self.metric is not None
                or self.metric_value is not None
            ):
                raise ValueError("IMPORTANCE_OBSERVATION_INVALID")
        elif (
            self.platform_id is None
            or self.snapshot_id is None
            or self.metric is None
            or self.metric_value is None
            or self.importance_level is not None
            or self.reason_codes
        ):
            raise ValueError("HEAT_OBSERVATION_INVALID")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("RANKING_REASON_DUPLICATED")
        return self


class RankedEventV2(_FrozenContract):
    event_id: str = Field(min_length=1, max_length=128)
    rank: int = Field(ge=1)
    mode: RankingMode
    score: float | None = None
    label: Literal[
        "importance",
        "importance_unknown",
        "platform_normalized_current_heat",
        "heat_unknown",
        "recency",
        "recency_unknown",
    ]
    basis: tuple[str, ...] = Field(default=(), max_length=64)
    trend_label: Literal["rising", "falling", "stable"] | None = None


class RankedEventsV2(_FrozenContract):
    mode: RankingMode
    items: tuple[RankedEventV2, ...] = Field(default=(), max_length=2_000)

    @model_validator(mode="after")
    def validate_ranks(self) -> RankedEventsV2:
        if tuple(item.rank for item in self.items) != tuple(
            range(1, len(self.items) + 1)
        ) or len({item.event_id for item in self.items}) != len(self.items):
            raise ValueError("EVENT_RANK_INVALID")
        return self


def rank_events(
    events: tuple[EventClusterV2, ...],
    ranking_mode: RankingMode,
    observations: tuple[EventRankingObservationV2, ...],
) -> RankedEventsV2:
    event_ids = [item.event_id for item in events]
    if len(set(event_ids)) != len(event_ids):
        raise ValueError("RANK_EVENT_DUPLICATED")
    if ranking_mode == "importance":
        items = _rank_importance(events, observations)
    elif ranking_mode == "heat":
        items = _rank_heat(events, observations)
    elif ranking_mode == "recency":
        items = _rank_recency(events)
    else:
        raise ValueError("RANKING_MODE_INVALID")
    return RankedEventsV2(mode=ranking_mode, items=items)


def _rank_importance(
    events: tuple[EventClusterV2, ...],
    observations: tuple[EventRankingObservationV2, ...],
) -> tuple[RankedEventV2, ...]:
    relevant: dict[str, EventRankingObservationV2] = {}
    known = {item.event_id for item in events}
    for observation in observations:
        if observation.observation_type != "importance" or observation.event_id not in known:
            continue
        if observation.event_id in relevant:
            raise ValueError("IMPORTANCE_OBSERVATION_DUPLICATED")
        relevant[observation.event_id] = observation
    ordered = sorted(
        events,
        key=lambda event: (
            -_importance_score(relevant.get(event.event_id)),
            -_timestamp(event.event_time),
            event.event_id,
        ),
    )
    result: list[RankedEventV2] = []
    for rank, event in enumerate(ordered, 1):
        current = relevant.get(event.event_id)
        score = _importance_score(current) if current is not None else None
        result.append(
            RankedEventV2(
                event_id=event.event_id,
                rank=rank,
                mode="importance",
                score=score,
                label="importance" if score is not None else "importance_unknown",
                basis=current.reason_codes if current is not None else (),
            )
        )
    return tuple(result)


def _rank_heat(
    events: tuple[EventClusterV2, ...],
    observations: tuple[EventRankingObservationV2, ...],
) -> tuple[RankedEventV2, ...]:
    normalized = _normalized_heat(observations)
    event_scores: dict[str, list[float]] = defaultdict(list)
    event_basis: dict[str, set[str]] = defaultdict(set)
    known = {item.event_id for item in events}
    for observation, score in normalized:
        if observation.event_id not in known:
            continue
        event_scores[observation.event_id].append(score)
        event_basis[observation.event_id].add(
            f"{observation.platform_id}:{observation.metric}:{observation.observed_at.isoformat()}"
        )
    average = {
        event_id: sum(values) / len(values)
        for event_id, values in event_scores.items()
    }
    ordered = sorted(
        events,
        key=lambda event: (
            event.event_id not in average,
            -average.get(event.event_id, 0.0),
            -_timestamp(event.event_time),
            event.event_id,
        ),
    )
    return tuple(
        RankedEventV2(
            event_id=event.event_id,
            rank=rank,
            mode="heat",
            score=average.get(event.event_id),
            label=(
                "platform_normalized_current_heat"
                if event.event_id in average
                else "heat_unknown"
            ),
            basis=tuple(sorted(event_basis.get(event.event_id, set()))),
            trend_label=None,
        )
        for rank, event in enumerate(ordered, 1)
    )


def _normalized_heat(
    observations: tuple[EventRankingObservationV2, ...],
) -> tuple[tuple[EventRankingObservationV2, float], ...]:
    heat = [item for item in observations if item.observation_type == "heat"]
    snapshots: dict[
        tuple[str, str, str], list[EventRankingObservationV2]
    ] = defaultdict(list)
    for item in heat:
        assert (
            item.platform_id is not None
            and item.metric is not None
            and item.snapshot_id is not None
        )
        snapshots[(item.platform_id, item.metric, item.snapshot_id)].append(item)
    selected: dict[tuple[str, str], list[EventRankingObservationV2]] = {}
    selected_at: dict[tuple[str, str], datetime] = {}
    for (platform_id, metric, _), members in snapshots.items():
        event_ids = [item.event_id for item in members]
        observed_at = {item.observed_at for item in members}
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("HEAT_OBSERVATION_DUPLICATED")
        if len(observed_at) != 1:
            raise ValueError("HEAT_SNAPSHOT_TIME_INCONSISTENT")
        group = (platform_id, metric)
        snapshot_time = members[0].observed_at
        if group not in selected_at or snapshot_time > selected_at[group]:
            selected[group] = members
            selected_at[group] = snapshot_time
        elif snapshot_time == selected_at[group]:
            raise ValueError("HEAT_SNAPSHOT_AMBIGUOUS")
    normalized: list[tuple[EventRankingObservationV2, float]] = []
    for (_, metric), members in sorted(selected.items()):
        values = [item.metric_value for item in members]
        assert all(value is not None for value in values)
        concrete = [float(value) for value in values if value is not None]
        low = min(concrete)
        high = max(concrete)
        for item in members:
            assert item.metric_value is not None
            if high == low:
                score = 0.5
            elif metric == "rank":
                score = (high - item.metric_value) / (high - low)
            else:
                score = (item.metric_value - low) / (high - low)
            normalized.append((item, score))
    return tuple(normalized)


def _rank_recency(
    events: tuple[EventClusterV2, ...],
) -> tuple[RankedEventV2, ...]:
    ordered = sorted(
        events,
        key=lambda event: (
            event.event_time is None,
            -_timestamp(event.event_time),
            event.event_id,
        ),
    )
    return tuple(
        RankedEventV2(
            event_id=event.event_id,
            rank=rank,
            mode="recency",
            score=_timestamp(event.event_time) if event.event_time is not None else None,
            label="recency" if event.event_time is not None else "recency_unknown",
            basis=(event.event_time.isoformat(),) if event.event_time is not None else (),
        )
        for rank, event in enumerate(ordered, 1)
    )


def _importance_score(observation: EventRankingObservationV2 | None) -> float:
    if observation is None or observation.importance_level is None:
        return 0.0
    return _IMPORTANCE_SCORE[observation.importance_level]


def _timestamp(value: datetime | None) -> float:
    return value.timestamp() if value is not None else 0.0


__all__ = [
    "EventRankingObservationV2",
    "RankedEventV2",
    "RankedEventsV2",
    "rank_events",
]
