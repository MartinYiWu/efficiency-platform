"""R06 可解释事件排序测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from efficiency_platform_agent.capabilities.research.v2.ranking import (
    EventRankingObservationV2,
    rank_events,
)
from efficiency_platform_agent.contracts.research_evidence_v2 import EventClusterV2


def _event(event_id: str, hour: int = 8) -> EventClusterV2:
    return EventClusterV2(
        event_id=event_id,
        event_type="product_release",
        entity_names=("Acme",),
        event_time=datetime(2026, 9, 15, hour, tzinfo=UTC),
        member_document_ids=(f"doc-{event_id}",),
        representative_document_id=f"doc-{event_id}",
        merge_basis=("singleton",),
        cluster_confidence="confirmed",
    )


def test_importance_uses_explicit_level_then_recency_and_stable_id() -> None:
    events = (_event("event-b", 8), _event("event-a", 8), _event("event-c", 9))
    observations = (
        EventRankingObservationV2(
            event_id="event-a",
            observation_type="importance",
            importance_level="high",
            reason_codes=("USER_ENTITY_MATCH",),
            observed_at=datetime(2026, 9, 16, tzinfo=UTC),
        ),
        EventRankingObservationV2(
            event_id="event-b",
            observation_type="importance",
            importance_level="high",
            reason_codes=("USER_ENTITY_MATCH",),
            observed_at=datetime(2026, 9, 16, tzinfo=UTC),
        ),
        EventRankingObservationV2(
            event_id="event-c",
            observation_type="importance",
            importance_level="medium",
            reason_codes=("TOPIC_MATCH",),
            observed_at=datetime(2026, 9, 16, tzinfo=UTC),
        ),
    )

    ranked = rank_events(events, "importance", observations)

    assert [item.event_id for item in ranked.items] == [
        "event-a",
        "event-b",
        "event-c",
    ]
    assert ranked.items[0].basis == ("USER_ENTITY_MATCH",)


def test_heat_is_normalized_per_platform_and_missing_is_unknown() -> None:
    events = tuple(_event(event_id) for event_id in ("event-a", "event-b", "event-c"))
    observed_at = datetime(2026, 9, 16, tzinfo=UTC)
    observations = (
        EventRankingObservationV2(
            event_id="event-a",
            observation_type="heat",
            snapshot_id="large-current",
            platform_id="platform-large",
            metric="score",
            metric_value=200,
            observed_at=observed_at,
        ),
        EventRankingObservationV2(
            event_id="event-b",
            observation_type="heat",
            snapshot_id="small-current",
            platform_id="platform-small",
            metric="score",
            metric_value=2,
            observed_at=observed_at,
        ),
        EventRankingObservationV2(
            event_id="event-x",
            observation_type="heat",
            snapshot_id="large-current",
            platform_id="platform-large",
            metric="score",
            metric_value=100,
            observed_at=observed_at,
        ),
        EventRankingObservationV2(
            event_id="event-y",
            observation_type="heat",
            snapshot_id="small-current",
            platform_id="platform-small",
            metric="score",
            metric_value=1,
            observed_at=observed_at,
        ),
    )

    ranked = rank_events(events, "heat", observations)

    assert [item.event_id for item in ranked.items] == [
        "event-a",
        "event-b",
        "event-c",
    ]
    assert ranked.items[0].score == ranked.items[1].score == 1.0
    assert ranked.items[2].score is None
    assert ranked.items[2].label == "heat_unknown"
    assert all(item.trend_label is None for item in ranked.items)
    assert "全网热度" not in " ".join(item.label for item in ranked.items)


def test_rank_metric_is_inverted_and_recency_has_no_fake_time() -> None:
    old = _event("old", 8)
    new = _event("new", 9)
    observations = (
        EventRankingObservationV2(
            event_id="old",
            observation_type="heat",
            snapshot_id="hn-current",
            platform_id="hn",
            metric="rank",
            metric_value=10,
            observed_at=datetime(2026, 9, 16, tzinfo=UTC),
        ),
        EventRankingObservationV2(
            event_id="new",
            observation_type="heat",
            snapshot_id="hn-current",
            platform_id="hn",
            metric="rank",
            metric_value=1,
            observed_at=datetime(2026, 9, 16, tzinfo=UTC),
        ),
    )

    heat = rank_events((old, new), "heat", observations)
    recency = rank_events((old, new), "recency", ())

    assert heat.items[0].event_id == "new"
    assert recency.items[0].event_id == "new"
