"""会话提交暂存器的一次性消费测试。"""

from __future__ import annotations

import pytest

from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
from efficiency_platform_agent.conversation.service import (
    ConversationService,
    ConversationSubmissionStore,
)
from efficiency_platform_agent.orchestration.scenario_resolver import ScenarioResolver
from tests.api.test_conversation_routes import RecordingRuntime, StubInterpreter, intent


class MutableClock:
    """测试提交暂存器 TTL 的可控单调时钟。"""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


@pytest.mark.asyncio
async def test_submission_is_tenant_isolated_and_deleted_after_successful_resolve() -> (
    None
):
    store = ConversationSubmissionStore()
    runtime = RecordingRuntime()
    facade = ConversationService(
        runtime=runtime,
        interpreter=StubInterpreter([intent()]),
        resolver=ScenarioResolver(),
        submissions=store,
    )
    await facade.submit(
        "conversation-1",
        "tenant-1",
        ConversationMessageV1(
            message="写内容", request_id="request-1", user_id="user-1"
        ),
    )
    await runtime.wait()
    submission = next(iter(store._entries.values())).submission

    with pytest.raises(ValueError, match="IDENTITY"):
        await store.resolve(submission.request, {"tenant_id": "tenant-2"})
    resolved = await store.resolve(submission.request, {"tenant_id": "tenant-1"})

    assert resolved is submission
    with pytest.raises(ValueError, match="NOT_FOUND"):
        await store.resolve(submission.request, {"tenant_id": "tenant-1"})


@pytest.mark.asyncio
async def test_submission_store_has_capacity_and_expiry_bounds() -> None:
    seed_store = ConversationSubmissionStore()
    runtime = RecordingRuntime()
    facade = ConversationService(
        runtime=runtime,
        interpreter=StubInterpreter([intent(), intent()]),
        resolver=ScenarioResolver(),
        submissions=seed_store,
    )
    for index in range(2):
        await facade.submit(
            f"conversation-{index}",
            "tenant-1",
            ConversationMessageV1(
                message="写内容",
                request_id=f"request-{index}",
                user_id="user-1",
            ),
        )
    await runtime.wait()
    submissions = [entry.submission for entry in seed_store._entries.values()]
    clock = MutableClock()
    bounded_store = ConversationSubmissionStore(
        max_entries=1, ttl_seconds=10, monotonic=clock
    )

    await bounded_store.put(submissions[0])
    with pytest.raises(ValueError, match="CAPACITY_EXCEEDED"):
        await bounded_store.put(submissions[1])

    clock.value = 11
    await bounded_store.put(submissions[1])
    assert len(bounded_store._entries) == 1
    with pytest.raises(ValueError, match="NOT_FOUND"):
        await bounded_store.resolve(submissions[0].request, {"tenant_id": "tenant-1"})
