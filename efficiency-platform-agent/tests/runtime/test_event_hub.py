"""进程内流事件总线的回放、订阅与安全边界测试。"""

from __future__ import annotations

import asyncio

import pytest

from efficiency_platform_agent.contracts.stream_events import RunStreamEventV1
from efficiency_platform_agent.runtime.event_hub import EventHub


def event(
    sequence: int,
    *,
    name: str = "assistant_delta",
    payload: dict[str, object] | None = None,
) -> RunStreamEventV1:
    """构造固定 Run 的测试事件。"""
    return RunStreamEventV1(
        event=name,
        run_id="run-1",
        sequence=sequence,
        payload=payload or {},
    )


@pytest.mark.asyncio
async def test_replay_returns_only_events_after_sequence() -> None:
    hub = EventHub()
    await hub.publish(event(1, name="run_started"))
    await hub.publish(event(2, payload={"delta": "第一段"}))
    await hub.publish(event(3, payload={"delta": "第二段"}))

    replayed = await hub.replay("run-1", after_sequence=1)

    assert [item.sequence for item in replayed] == [2, 3]


@pytest.mark.asyncio
async def test_subscriber_receives_new_event_and_can_close() -> None:
    hub = EventHub()
    subscription = hub.subscribe("run-1")

    await hub.publish(event(1, name="run_started"))

    assert (await asyncio.wait_for(anext(subscription), 0.2)).sequence == 1
    await subscription.aclose()
    assert hub.subscriber_count("run-1") == 0


@pytest.mark.asyncio
async def test_payload_mutation_is_isolated_between_publish_history_and_subscribers() -> (
    None
):
    hub = EventHub()
    first = hub.subscribe("run-1")
    second = hub.subscribe("run-1")
    published = event(1, payload={"nested": {"items": ["原值"]}})

    await hub.publish(published)
    published.payload["nested"]["items"].append("发布方污染")  # type: ignore[index,union-attr]
    first_event = await anext(first)
    first_event.payload["nested"]["items"].append("订阅方污染")  # type: ignore[index,union-attr]
    second_event = await anext(second)
    replayed = (await hub.replay("run-1", 0))[0]

    assert second_event.payload == {"nested": {"items": ["原值"]}}
    assert replayed.payload == {"nested": {"items": ["原值"]}}
    replayed.payload["nested"]["items"].append("回放方污染")  # type: ignore[index,union-attr]
    assert (await hub.replay("run-1", 0))[0].payload == {"nested": {"items": ["原值"]}}
    await first.aclose()
    await second.aclose()


@pytest.mark.asyncio
async def test_publish_next_assigns_monotonic_sequence_across_publishers() -> None:
    hub = EventHub()

    published = await asyncio.gather(
        *(
            hub.publish_next("run-1", "assistant_delta", {"delta": str(i)})
            for i in range(5)
        )
    )

    assert sorted(item.sequence for item in published) == [1, 2, 3, 4, 5]
    assert [item.sequence for item in await hub.replay("run-1", 0)] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_stream_done_closes_history_and_rejects_late_event() -> None:
    hub = EventHub()
    await hub.publish(event(1, name="run_started"))
    await hub.publish(event(2, name="stream_done", payload={"status": "succeeded"}))

    assert hub.is_closed("run-1") is True
    with pytest.raises(ValueError, match="已经结束"):
        await hub.publish(event(3))


@pytest.mark.asyncio
async def test_publish_rejects_non_monotonic_sequence() -> None:
    hub = EventHub()
    await hub.publish(event(2, name="run_started"))

    with pytest.raises(ValueError, match="必须递增"):
        await hub.publish(event(2))


@pytest.mark.parametrize(
    "payload,sensitive_value",
    [
        (
            {"api_key": "sk-test-value-must-not-be-echoed"},
            "sk-test-value-must-not-be-echoed",
        ),
        ({"message": "postgresql://user:password@db/runtime"}, "password"),
        ({"detail": "Traceback (most recent call last): internal"}, "internal"),
        ({"nested": {"exception": "provider-private-error"}}, "provider-private-error"),
        (
            {"nested": [{"model_candidates": ["private-model"]}]},
            "private-model",
        ),
        ({"nested": {"tool_args": {"query": "private-query"}}}, "private-query"),
        ({"nested": [{"raw-page": "private-page"}]}, "private-page"),
        (
            {"nested": {"items": [{"hidden_reasoning": "private-reason"}]}},
            "private-reason",
        ),
    ],
)
@pytest.mark.asyncio
async def test_publish_rejects_sensitive_payload_without_echoing_value(
    payload: dict[str, object], sensitive_value: str
) -> None:
    hub = EventHub()

    with pytest.raises(ValueError) as captured:
        await hub.publish(event(1, payload=payload))

    assert sensitive_value not in str(captured.value)


@pytest.mark.asyncio
async def test_publish_rejects_nested_camel_case_model_candidates_key() -> None:
    hub = EventHub()

    with pytest.raises(ValueError, match="敏感信息"):
        await hub.publish(
            event(1, payload={"nested": {"modelCandidates": ["private"]}})
        )


@pytest.mark.asyncio
async def test_publish_rejects_nested_camel_case_tool_args_key() -> None:
    hub = EventHub()

    with pytest.raises(ValueError, match="敏感信息"):
        await hub.publish(
            event(1, payload={"nested": [{"toolArgs": {"q": "private"}}]})
        )


@pytest.mark.asyncio
async def test_publish_rejects_nested_camel_case_raw_page_key() -> None:
    hub = EventHub()

    with pytest.raises(ValueError, match="敏感信息"):
        await hub.publish(event(1, payload={"nested": {"rawPage": "private"}}))


@pytest.mark.asyncio
async def test_publish_rejects_nested_pascal_case_hidden_reasoning_key() -> None:
    hub = EventHub()

    with pytest.raises(ValueError, match="敏感信息"):
        await hub.publish(
            event(1, payload={"nested": [{"HiddenReasoning": "private"}]})
        )


@pytest.mark.asyncio
async def test_publish_allows_normal_business_text_containing_token_word() -> None:
    """结构化 token 键受禁，但普通业务正文中的同名单词不应误伤。"""

    hub = EventHub()

    await hub.publish(
        event(1, payload={"delta": "本周讨论 token economy 与用户激励机制。"})
    )

    assert (await hub.replay("run-1", 0))[0].payload["delta"].startswith("本周讨论")
