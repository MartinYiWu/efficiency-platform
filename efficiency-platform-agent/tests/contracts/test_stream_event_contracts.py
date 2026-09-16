"""流事件与运营交付物契约的边界测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.deliverables import DeliverableV1
from efficiency_platform_agent.contracts.stream_events import RunStreamEventV1


def test_stream_event_rejects_unknown_event_name() -> None:
    with pytest.raises(ValidationError):
        RunStreamEventV1(
            event="not_registered",
            run_id="run-1",
            sequence=1,
            payload={},
        )


@pytest.mark.parametrize(
    "event_name",
    [
        "run_started",
        "intent_detected",
        "clarification_required",
        "phase_started",
        "assistant_started",
        "assistant_delta",
        "deliverable",
        "usage_update",
        "stream_error",
        "stream_done",
    ],
)
def test_stream_event_accepts_every_registered_event_name(event_name: str) -> None:
    event = RunStreamEventV1(event=event_name, run_id="run-1", sequence=1, payload={})

    assert event.event == event_name


def test_stream_event_rejects_unknown_contract_version() -> None:
    with pytest.raises(ValidationError):
        RunStreamEventV1(
            contract_version="run.stream.event/2",
            event="run_started",
            run_id="run-1",
            sequence=1,
        )


def test_stream_event_requires_run_id() -> None:
    with pytest.raises(ValidationError):
        RunStreamEventV1(event="run_started", sequence=1, payload={})


@pytest.mark.parametrize("value", [datetime.now(UTC), b"secret", {"a"}, ("tuple",)])
def test_stream_event_rejects_non_json_nested_values(value: object) -> None:
    with pytest.raises(ValidationError):
        RunStreamEventV1(
            event="assistant_delta",
            run_id="run-1",
            sequence=1,
            payload={"nested": {"value": value}},
        )


def test_stream_event_takes_an_isolated_json_snapshot_and_round_trips() -> None:
    payload = {"nested": {"items": ["first"]}}
    event = RunStreamEventV1(
        event="assistant_delta", run_id="run-1", sequence=1, payload=payload
    )

    payload["nested"]["items"].append("later")

    assert event.payload["nested"] == {"items": ["first"]}
    assert RunStreamEventV1.model_validate_json(event.model_dump_json()) == event


def test_deliverable_requires_platform() -> None:
    with pytest.raises(ValidationError):
        DeliverableV1(title="标题", body="正文")


def test_deliverable_set_contains_controlled_citations_and_summary() -> None:
    from efficiency_platform_agent.contracts.deliverables import (
        CitationV1,
        DeliverableSetV1,
    )

    result = DeliverableSetV1(
        deliverables=[
            DeliverableV1(
                platform="xiaohongshu",
                title="标题",
                body="正文",
                citations=[CitationV1(url="https://example.com", title="来源")],
            )
        ],
        summary="已完成",
        degraded=False,
    )

    assert result.deliverables[0].citations[0].url == "https://example.com"
    with pytest.raises(ValidationError):
        DeliverableV1(
            platform="xiaohongshu",
            title="标题",
            body="正文",
            citations=[{"url": "https://example.com", "unexpected": "x"}],
        )
