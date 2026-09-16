"""通用对话 Agent 的统一模型运行时契约测试。"""

from __future__ import annotations

import inspect
from dataclasses import fields, replace

import pytest

from efficiency_platform_agent.agents.conversation.general_agent import (
    GeneralConversationAgent,
    GeneralConversationError,
)
from efficiency_platform_agent.contracts.direct_conversation import (
    DirectConversationSubmission,
)
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.model import (
    ModelCandidate,
    ModelExecutionResult,
    ModelSelection,
    ModelTier,
)
from efficiency_platform_agent.core.run import (
    ProviderError,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
    RunRequest,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot


def _budget() -> RemainingBudget:
    return RemainingBudget(2, 0, 20_000, 2_000, 100_000, 15_000)


def _submission() -> DirectConversationSubmission:
    return DirectConversationSubmission(
        contract_version="direct-conversation/1",
        request=RunRequest(
            "request-1", "tenant-1", "user-1", "那我刚才问的核心是什么？"
        ),
        visible_history=(
            ProviderMessage("user", "请解释内容定位。"),
            ProviderMessage("assistant", "内容定位需要明确受众与价值。"),
        ),
        current_message="那我刚才问的核心是什么？",
        local_response=None,
        remaining_budget=_budget(),
    )


def _execution(
    *,
    content: str | None = "核心是明确受众与价值。",
    error: ProviderError | None = None,
    degraded: bool = True,
    role: str = "assistant",
) -> ModelExecutionResult:
    usage = ProviderUsage(18, 9, 0, 0, 7)
    result = ProviderResult(
        "general-conversation/1",
        ProviderMessage(role, content) if content is not None else None,
        usage,
        error,
    )
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
        result,
        (ModelSelection(candidate, 1, ModelTier.STRONG, "degraded"),),
        UsageSnapshot(18, 9, 7, False),
        degraded,
    )


class FakeModelRuntime:
    """记录统一 complete 三参数调用并返回脚本结果。"""

    def __init__(self, execution: ModelExecutionResult) -> None:
        self.execution = execution
        self.calls: list[tuple[object, ProviderRequest, RemainingBudget]] = []

    async def complete(self, demand, request, *, remaining_budget):
        self.calls.append((demand, request, remaining_budget))
        return self.execution


class StreamingModelRuntime(FakeModelRuntime):
    """以同步于模型执行期的回调模拟真实流式 Runtime。"""

    def __init__(self, execution: ModelExecutionResult) -> None:
        super().__init__(execution)
        self.stream_calls: list[tuple[object, ProviderRequest, RemainingBudget]] = []

    async def stream_complete(self, demand, request, *, remaining_budget, on_delta):
        """先交付两个 delta，再返回完整模型执行结果。"""
        self.stream_calls.append((demand, request, remaining_budget))
        for delta in ("核心是", "明确受众与价值。"):
            delivered = on_delta(delta)
            if inspect.isawaitable(delivered):
                await delivered
        return self.execution


class RaisingModelRuntime:
    """模拟统一运行时内部异常，异常正文不得越过 Agent 边界。"""

    async def complete(self, demand, request, *, remaining_budget):
        del demand, request, remaining_budget
        raise RuntimeError("包含不应外泄的厂商异常正文")


class DirectProvider:
    """缺少 demand 与 remaining_budget 的旧 Provider 接口。"""

    async def complete(self, request):
        return request


class InvalidModelRuntime:
    """返回非统一执行结果，验证 Agent 在边界失败关闭。"""

    async def complete(self, demand, request, *, remaining_budget):
        del demand, request, remaining_budget
        return object()


@pytest.mark.asyncio
async def test_general_agent_uses_visible_history_and_returns_content() -> None:
    runtime = FakeModelRuntime(_execution())
    agent = GeneralConversationAgent(runtime)

    execution = await agent.execute(_submission())

    assert execution.content == "核心是明确受众与价值。"
    assert execution.usage == UsageSnapshot(18, 9, 7, False)
    assert execution.degraded is True
    assert {field.name for field in fields(execution)} == {
        "content",
        "usage",
        "degraded",
        "attempts",
    }
    assert len(runtime.calls) == 1
    demand, request, remaining = runtime.calls[0]
    assert remaining == _budget()
    assert demand.requires_structured_output is False
    assert demand.requires_tools is False
    assert [message.role for message in request.messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert request.messages[1:3] == _submission().visible_history
    assert request.messages[-1].content == _submission().current_message
    assert "AI 内容运营助手" in str(request.messages[0].content)
    assert "不可信数据" in str(request.messages[0].content)


@pytest.mark.asyncio
async def test_general_agent_prefers_stream_runtime_and_returns_published_content() -> (
    None
):
    """流式 Runtime 可用时，delta 必须在完整结果前经 Agent 回调发布。"""
    runtime = StreamingModelRuntime(_execution(content="核心是明确受众与价值。"))
    received: list[str] = []

    execution = await GeneralConversationAgent(runtime).execute(
        _submission(), on_delta=received.append
    )

    assert runtime.calls == []
    assert len(runtime.stream_calls) == 1
    assert received == ["核心是", "明确受众与价值。"]
    assert execution.content == "".join(received)


@pytest.mark.asyncio
async def test_general_agent_uses_positive_product_persona_without_base_limitations() -> None:
    runtime = FakeModelRuntime(_execution())

    await GeneralConversationAgent(runtime).execute(_submission())

    system_prompt = str(runtime.calls[0][1].messages[0].content)
    assert "公开资料" in system_prompt
    assert "来源" in system_prompt
    assert "不得声称已经联网检索" not in system_prompt
    assert "需要进入受治理的运营研究能力" not in system_prompt


@pytest.mark.asyncio
async def test_general_agent_governs_base_limitation_in_model_output() -> None:
    runtime = FakeModelRuntime(_execution(content="我不能真正联网，也不能生成文件。"))

    execution = await GeneralConversationAgent(runtime).execute(_submission())

    assert "公开资料整理" in execution.content
    assert execution.content != "我不能真正联网，也不能生成文件。"


def test_general_agent_rejects_direct_provider_bypass() -> None:
    with pytest.raises(TypeError, match="GeneralConversationModelRuntime"):
        GeneralConversationAgent(DirectProvider())


@pytest.mark.asyncio
async def test_general_agent_normalizes_missing_content_model_error_without_leaking_details() -> (
    None
):
    provider_error = ProviderError(
        "VENDOR_SECRET_FAILURE",
        "provider",
        False,
        "不应直接展示的厂商消息",
    )
    execution = _execution(content=None, error=provider_error)
    assert execution.result.message is None
    agent = GeneralConversationAgent(FakeModelRuntime(execution))

    with pytest.raises(GeneralConversationError) as captured:
        await agent.execute(_submission())

    assert captured.value.code == "GENERAL_CONVERSATION_MODEL_FAILED"
    assert captured.value.safe_message == "通用对话模型暂时无法完成回答"
    assert captured.value.usage == UsageSnapshot(18, 9, 7, False)
    assert captured.value.degraded is True
    assert "VENDOR_SECRET_FAILURE" not in str(captured.value)
    assert "厂商消息" not in str(captured.value)


@pytest.mark.asyncio
async def test_general_agent_normalizes_runtime_exception() -> None:
    agent = GeneralConversationAgent(RaisingModelRuntime())

    with pytest.raises(GeneralConversationError) as captured:
        await agent.execute(_submission())

    assert captured.value.code == "GENERAL_CONVERSATION_MODEL_FAILED"
    assert captured.value.usage == UsageSnapshot()
    assert captured.value.degraded is False
    assert "厂商异常正文" not in str(captured.value)


@pytest.mark.asyncio
async def test_general_agent_rejects_non_assistant_model_message() -> None:
    agent = GeneralConversationAgent(FakeModelRuntime(_execution(role="user")))

    with pytest.raises(GeneralConversationError) as captured:
        await agent.execute(_submission())

    assert captured.value.code == "GENERAL_CONVERSATION_MODEL_FAILED"


@pytest.mark.asyncio
async def test_general_agent_rejects_blank_model_content_and_keeps_usage() -> None:
    agent = GeneralConversationAgent(FakeModelRuntime(_execution(content="   ")))

    with pytest.raises(GeneralConversationError) as captured:
        await agent.execute(_submission())

    assert captured.value.code == "GENERAL_CONVERSATION_MODEL_FAILED"
    assert captured.value.usage == UsageSnapshot(18, 9, 7, False)
    assert captured.value.degraded is True


@pytest.mark.asyncio
async def test_general_agent_rejects_invalid_runtime_result() -> None:
    agent = GeneralConversationAgent(InvalidModelRuntime())

    with pytest.raises(GeneralConversationError) as captured:
        await agent.execute(_submission())

    assert captured.value.code == "GENERAL_CONVERSATION_MODEL_FAILED"
    assert captured.value.usage == UsageSnapshot()
    assert captured.value.degraded is False


@pytest.mark.asyncio
async def test_general_agent_caps_request_to_low_positive_remaining_budget() -> None:
    low_budget = RemainingBudget(1, 0, 20_000, 1, 100_000, 1)
    runtime = FakeModelRuntime(_execution())
    submission = replace(_submission(), remaining_budget=low_budget)

    await GeneralConversationAgent(runtime).execute(submission)

    demand, request, remaining = runtime.calls[0]
    assert demand.max_output_tokens == 1
    assert dict(request.options.items)["max_tokens"] == 1
    assert request.timeout_ms == 1
    assert remaining == low_budget


def test_submission_rejects_hidden_roles_and_unbounded_history() -> None:
    base = _submission()
    with pytest.raises(ValueError, match="可见历史"):
        DirectConversationSubmission(
            base.contract_version,
            base.request,
            (ProviderMessage("system", "隐藏系统消息"),),
            base.current_message,
            None,
            base.remaining_budget,
        )
    with pytest.raises(ValueError, match="可见历史"):
        DirectConversationSubmission(
            base.contract_version,
            base.request,
            tuple(ProviderMessage("user", str(index)) for index in range(9)),
            base.current_message,
            None,
            base.remaining_budget,
        )


def test_submission_accepts_12000_history_characters_and_rejects_12001() -> None:
    base = _submission()
    accepted = replace(base, visible_history=(ProviderMessage("user", "甲" * 12_000),))

    assert len(str(accepted.visible_history[0].content)) == 12_000
    with pytest.raises(ValueError, match="可见历史超过字符上限"):
        replace(base, visible_history=(ProviderMessage("user", "甲" * 12_001),))


@pytest.mark.parametrize(
    "budget",
    [
        RemainingBudget(0, 0, 20_000, 2_000, 100_000, 15_000),
        RemainingBudget(2, 0, 0, 2_000, 100_000, 15_000),
        RemainingBudget(2, 0, 20_000, 0, 100_000, 15_000),
        RemainingBudget(2, 0, 20_000, 2_000, 100_000, 0),
    ],
)
def test_submission_rejects_exhausted_model_budget(
    budget: RemainingBudget,
) -> None:
    with pytest.raises(ValueError, match="剩余预算不足"):
        replace(_submission(), remaining_budget=budget)
