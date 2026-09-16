"""运行事件的稳定类型、白名单与安全边界测试。"""

from __future__ import annotations

import pytest

from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.core.run import JsonObject
from efficiency_platform_agent.core.runtime import RunEventRecord


def make_event(
    event_type: str = "run_started", payload: JsonObject | None = None
) -> RunEventRecord:
    """构造合成运行事件。"""
    return RunEventRecord(
        event_id="event-1",
        event_type=event_type,
        run_id="run-1",
        tenant_id="tenant-1",
        sequence=1,
        occurred_at_epoch_ms=1_001,
        status=RunStatus.RUNNING,
        payload=JsonObject() if payload is None else payload,
    )


def test_event_fields_are_positive_and_payload_is_immutable() -> None:
    """事件 ID、类型、序号和时间必须有效，payload 使用 JsonObject。"""
    event = make_event()
    assert event.sequence == 1
    with pytest.raises(TypeError):
        make_event(payload={"unsafe": True})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        RunEventRecord("", "run_started", "run-1", "tenant-1", 1, 1, RunStatus.RUNNING)


def test_strategy_event_rejects_unknown_evidence_key() -> None:
    """strategy_event 只能使用冻结的证据字段白名单。"""
    with pytest.raises(ValueError):
        make_event(
            "strategy_event",
            JsonObject((("strategy_event_type", "task"), ("secret", "no"))),
        )


def test_strategy_event_accepts_frozen_evidence_fields() -> None:
    """合法 strategy_event 证据字段可被构造。"""
    event = make_event(
        "strategy_event",
        JsonObject(
            (
                ("strategy_event_type", "task_completed"),
                ("graph_id", "direct"),
                ("attempt", 1),
                ("counts", JsonObject((("completed", 1),))),
            )
        ),
    )
    assert event.event_type == "strategy_event"


@pytest.mark.parametrize(
    "sensitive_key",
    [
        "input_text",
        "rendered_prompt",
        "prompt",
        "arguments",
        "exception",
        "secret",
        "provider_script",
    ],
)
def test_event_rejects_sensitive_keys_nested_in_json_containers(
    sensitive_key: str,
) -> None:
    """事件 payload 在嵌套 JsonObject/tuple 中也不得携带敏感正文键。"""
    payload = JsonObject((("meta", (JsonObject(((sensitive_key, "secret"),)),)),))
    with pytest.raises(ValueError):
        make_event(payload=payload)


def test_strategy_event_rejects_unknown_nested_envelope_key() -> None:
    """strategy_event 的白名单约束不得被嵌套对象绕过。"""
    payload = JsonObject((("meta", JsonObject((("unregistered", "value"),))),))
    with pytest.raises(ValueError):
        make_event("strategy_event", payload)
