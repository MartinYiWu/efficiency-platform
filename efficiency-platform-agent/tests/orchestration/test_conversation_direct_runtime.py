"""通用对话 DIRECT Graph 与一次性提交存储测试。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from efficiency_platform_agent.agents.conversation.general_agent import (
    GeneralConversationAgent,
)
from efficiency_platform_agent.contracts.direct_conversation import (
    DirectConversationSubmission,
)
from efficiency_platform_agent.conversation.direct_submission import (
    DirectConversationSubmissionError,
    DirectConversationSubmissionStore,
)
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.model import (
    ModelCandidate,
    ModelExecutionResult,
    ModelSelection,
    ModelTier,
)
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderError,
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
    RunRequest,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.orchestration.builders.conversation_direct import (
    build_conversation_direct_registration,
)
from efficiency_platform_agent.orchestration.registry import GraphRegistry
from efficiency_platform_agent.orchestration.runtime import GraphRuntime
from efficiency_platform_agent.routing.strategy_router import StrategySelection


def _budget() -> RemainingBudget:
    return RemainingBudget(2, 0, 20_000, 2_000, 100_000, 15_000)


def _submission(*, local_response: str | None = None) -> DirectConversationSubmission:
    return DirectConversationSubmission(
        "direct-conversation/1",
        RunRequest("request-1", "tenant-1", "user-1", "继续解释"),
        (ProviderMessage("assistant", "之前讨论了内容定位。"),),
        "继续解释",
        local_response,
        _budget(),
    )


class FakeModelRuntime:
    """返回固定自然语言正文并记录调用次数。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def complete(self, demand, request, *, remaining_budget):
        del demand, request, remaining_budget
        self.calls += 1
        usage = ProviderUsage(11, 6, 0, 0, 3)
        candidate = ModelCandidate(
            "fake-balanced",
            "fake-provider",
            "balanced",
            ModelTier.BALANCED,
            False,
            False,
            32_000,
            True,
            False,
        )
        if self.fail:
            result = ProviderResult(
                "general-conversation/1",
                None,
                usage,
                ProviderError("DOWN", "server_error", True, "内部失败"),
            )
        else:
            result = ProviderResult(
                "general-conversation/1",
                ProviderMessage("assistant", "这是模型生成的普通聊天回答。"),
                usage,
            )
        return ModelExecutionResult(
            result,
            (ModelSelection(candidate, 1, None, "requested_tier"),),
            UsageSnapshot(11, 6, 3, False),
            False,
        )


class StreamingModelRuntime(FakeModelRuntime):
    """通过 Runtime 回调交付两段模型正文。"""

    async def stream_complete(self, demand, request, *, remaining_budget, on_delta):
        """在返回完整结果前交付可见 delta。"""
        del demand, request, remaining_budget
        self.calls += 1
        for delta in ("模型实时", "正文。"):
            await on_delta(delta)
        usage = ProviderUsage(11, 6, 0, 0, 3)
        candidate = ModelCandidate(
            "fake-balanced",
            "fake-provider",
            "balanced",
            ModelTier.BALANCED,
            False,
            False,
            32_000,
            True,
            False,
        )
        return ModelExecutionResult(
            ProviderResult(
                "general-conversation/1",
                ProviderMessage("assistant", "模型实时正文。"),
                usage,
            ),
            (ModelSelection(candidate, 1, None, "requested_tier"),),
            UsageSnapshot(11, 6, 3, False),
            False,
        )


class MutableClock:
    """测试提交 TTL 的可控单调时钟。"""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _state(*, user_id: str = "user-1") -> dict[str, object]:
    return {
        "run_id": "run-1",
        "tenant_id": "tenant-1",
        "user_id": user_id,
        "request_id": "request-1",
        "input_text": "继续解释",
        "strategy": "direct",
        "strategy_payload_schema_version": "strategy.none/1",
        "strategy_payload": JsonObject(),
    }


async def _execute(
    submission: DirectConversationSubmission,
    model_runtime: FakeModelRuntime,
    *,
    state: dict[str, object] | None = None,
):
    store = DirectConversationSubmissionStore()
    await store.put(submission)
    registry = GraphRegistry()
    registration = build_conversation_direct_registration(
        GeneralConversationAgent(model_runtime), store.resolve
    )
    registry.register(registration)
    runtime = GraphRuntime(registry)
    result = await runtime.execute(
        StrategySelection(StrategyMode.DIRECT, "general_chat", "test"),
        state or _state(),
    )
    return result, registration, store


@pytest.mark.asyncio
async def test_local_response_does_not_call_model_and_output_only_has_content() -> None:
    model_runtime = FakeModelRuntime()

    result, registration, _ = await _execute(
        _submission(local_response="你好，我是 AI 内容运营助手。"), model_runtime
    )

    assert result.next_status is RunStatus.SUCCEEDED
    assert dict(result.output.items) == {"content": "你好，我是 AI 内容运营助手。"}
    assert result.usage == UsageSnapshot()
    assert result.degraded is False
    assert model_runtime.calls == 0
    assert registration.strategy is StrategyMode.DIRECT
    assert registration.checkpoint_ns == "s2:direct:1"
    assert registration.allowed_strategy_payload_keys == frozenset()


@pytest.mark.asyncio
async def test_general_chat_calls_model_and_preserves_usage_and_degraded() -> None:
    model_runtime = FakeModelRuntime()

    result, _, _ = await _execute(_submission(), model_runtime)

    assert result.next_status is RunStatus.SUCCEEDED
    assert dict(result.output.items) == {
        "content": "这是模型生成的普通聊天回答。"
    }
    assert result.usage == UsageSnapshot(11, 6, 3, False)
    assert result.degraded is False
    assert model_runtime.calls == 1


@pytest.mark.asyncio
async def test_direct_graph_publishes_streamed_deltas_through_run_scoped_port() -> None:
    """Graph 只通过 run_id 隔离的窄端口转发 Agent 的实时正文。"""
    model_runtime = StreamingModelRuntime()
    store = DirectConversationSubmissionStore()
    await store.put(_submission())
    delivered: list[tuple[str, str]] = []

    async def publish(run_id: str, delta: str) -> None:
        """记录 Graph 输出端口收到的运行标识和正文。"""
        delivered.append((run_id, delta))

    registry = GraphRegistry()
    registration = build_conversation_direct_registration(
        GeneralConversationAgent(model_runtime),
        store.resolve,
        output_publisher=publish,
    )
    registry.register(registration)
    result = await GraphRuntime(registry).execute(
        StrategySelection(StrategyMode.DIRECT, "general_chat", "test"), _state()
    )

    assert delivered == [("run-1", "模型实时"), ("run-1", "正文。")]
    assert dict(result.output.items) == {"content": "模型实时正文。"}


@pytest.mark.asyncio
async def test_direct_graph_rejects_user_identity_mismatch_without_consuming() -> None:
    model_runtime = FakeModelRuntime()

    result, _, store = await _execute(
        _submission(), model_runtime, state=_state(user_id="user-2")
    )

    assert result.next_status is RunStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "DIRECT_CONVERSATION_IDENTITY_MISMATCH"
    assert result.output is None
    assert model_runtime.calls == 0
    resolved = await store.resolve(
        _submission().request,
        {"tenant_id": "tenant-1", "user_id": "user-1", "request_id": "request-1"},
    )
    assert resolved == _submission()


@pytest.mark.asyncio
async def test_direct_graph_normalizes_model_failure_and_keeps_usage() -> None:
    model_runtime = FakeModelRuntime(fail=True)

    result, _, _ = await _execute(_submission(), model_runtime)

    assert result.next_status is RunStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "GENERAL_CONVERSATION_MODEL_FAILED"
    assert result.output is None
    assert result.usage == UsageSnapshot(11, 6, 3, False)


@pytest.mark.asyncio
async def test_submission_store_discards_and_rejects_wrong_tenant() -> None:
    store = DirectConversationSubmissionStore()
    submission = _submission()
    await store.put(submission)

    with pytest.raises(DirectConversationSubmissionError) as captured:
        await store.resolve(
            submission.request,
            {"tenant_id": "tenant-2", "user_id": "user-1", "request_id": "request-1"},
        )
    assert captured.value.code == "DIRECT_CONVERSATION_IDENTITY_MISMATCH"

    await store.discard("tenant-1", "request-1")
    with pytest.raises(DirectConversationSubmissionError) as missing:
        await store.resolve(
            submission.request,
            {"tenant_id": "tenant-1", "user_id": "user-1", "request_id": "request-1"},
        )
    assert missing.value.code == "DIRECT_CONVERSATION_SUBMISSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_submission_store_consumes_each_submission_only_once() -> None:
    store = DirectConversationSubmissionStore()
    submission = _submission()
    state = {"tenant_id": "tenant-1", "user_id": "user-1", "request_id": "request-1"}
    await store.put(submission)

    assert await store.resolve(submission.request, state) == submission
    with pytest.raises(DirectConversationSubmissionError) as captured:
        await store.resolve(submission.request, state)
    assert captured.value.code == "DIRECT_CONVERSATION_SUBMISSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_submission_store_rejects_conflicting_value_for_the_same_key() -> None:
    store = DirectConversationSubmissionStore()
    await store.put(_submission())

    with pytest.raises(DirectConversationSubmissionError) as captured:
        await store.put(replace(_submission(), local_response="不同提交"))

    assert captured.value.code == "DIRECT_CONVERSATION_SUBMISSION_CONFLICT"


@pytest.mark.asyncio
async def test_submission_store_expires_entries_at_ttl_boundary() -> None:
    clock = MutableClock()
    store = DirectConversationSubmissionStore(ttl_seconds=10, monotonic=clock)
    submission = _submission()
    await store.put(submission)

    clock.value = 10
    with pytest.raises(DirectConversationSubmissionError) as captured:
        await store.resolve(
            submission.request,
            {"tenant_id": "tenant-1", "user_id": "user-1", "request_id": "request-1"},
        )
    assert captured.value.code == "DIRECT_CONVERSATION_SUBMISSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_submission_store_rejects_new_entry_at_capacity() -> None:
    store = DirectConversationSubmissionStore(max_entries=1)
    first = _submission()
    second = replace(
        first,
        request=RunRequest("request-2", "tenant-1", "user-1", "继续解释"),
    )
    await store.put(first)

    with pytest.raises(DirectConversationSubmissionError) as captured:
        await store.put(second)

    assert captured.value.code == "DIRECT_CONVERSATION_SUBMISSION_CAPACITY_EXCEEDED"
