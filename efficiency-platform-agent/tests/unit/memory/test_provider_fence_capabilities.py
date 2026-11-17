"""最终栅栏必须保留真实Provider能力，不能把complete-only变成流式。"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.ports import StreamingModelProvider
from efficiency_platform_agent.core.run import (
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.core.run_context_binding import bind_run_context
from efficiency_platform_agent.harness.local_real_factory import (
    build_local_agent_application,
)
from efficiency_platform_agent.orchestration.context_gate import FencedModelProvider
from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
from tests.orchestration.test_conversation_direct_runtime import _submission
from tests.unit.harness.test_local_real_factory import synthetic_settings


class Gate:
    def __init__(self):
        self.blocked = False
        self.held = False
        self.enters = 0
        self.exits = 0

    @asynccontextmanager
    async def guard_execution(self, *args):
        if self.blocked:
            raise PermissionError("MEMORY_THREAD_FENCED")
        self.held = True
        self.enters += 1
        try:
            yield
        finally:
            self.held = False
            self.exits += 1


def binding():
    return SimpleNamespace(
        memory_context=object(),
        conversation=SimpleNamespace(tenant_id="synthetic-tenant"),
        execution_id="synthetic-java-exec",
    )


def provider_result():
    return ProviderResult(
        "general-conversation/1",
        ProviderMessage("assistant", "synthetic-complete-result"),
        ProviderUsage(2, 3, 0, 0, 0),
    )


def test_only_complete_provider_does_not_gain_structural_stream_capability():
    provider = FakeModelProvider("synthetic-complete", [provider_result()])
    assert not isinstance(provider, StreamingModelProvider)
    wrapped = FencedModelProvider(provider, Gate(), "official")
    assert not isinstance(wrapped, StreamingModelProvider)
    assert not hasattr(wrapped, "stream")


async def test_real_factory_general_conversation_uses_only_complete_provider_with_delta_callback():
    provider = FakeModelProvider("synthetic-complete", [provider_result()])
    gate = Gate()
    bundle = build_local_agent_application(
        synthetic_settings(),
        provider=FencedModelProvider(provider, gate, "official"),
        test_mode=True,
    )
    agent = bundle.runtime.graph_runtime.registry.get(StrategyMode.DIRECT).builder.agent
    deltas = []
    with bind_run_context(binding()):
        execution = await agent.execute(_submission(), on_delta=deltas.append)
    assert execution.content == "synthetic-complete-result"
    assert provider._index == 1
    assert gate.enters == gate.exits == 1 and not gate.held


async def test_streaming_wrapper_keeps_guard_until_inner_iterator_closed():
    gate = Gate()

    class StreamingBoundary(FakeModelProvider):
        closed = False

        async def stream(self, request):
            assert gate.held
            try:
                yield "synthetic-first"
                yield "synthetic-last"
            finally:
                assert gate.held
                self.closed = True

    provider = StreamingBoundary("synthetic-stream", [])
    wrapped = FencedModelProvider(provider, gate, "official")
    assert isinstance(wrapped, StreamingModelProvider)
    with bind_run_context(binding()):
        stream = wrapped.stream(None)
        assert await anext(stream) == "synthetic-first"
        assert gate.held
        await stream.aclose()
    assert provider.closed and not gate.held and gate.exits == 1


async def test_stream_cancellation_closes_inner_and_fenced_complete_never_sends():
    gate = Gate()
    entered = asyncio.Event()

    class StreamingBoundary(FakeModelProvider):
        closed = False

        async def stream(self, request):
            try:
                entered.set()
                await asyncio.Event().wait()
                yield "unreachable"
            finally:
                assert gate.held
                self.closed = True

    provider = StreamingBoundary("synthetic-stream", [])
    wrapped = FencedModelProvider(provider, gate, "official")
    with bind_run_context(binding()):
        stream = wrapped.stream(None)
        task = asyncio.create_task(anext(stream))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert provider.closed and gate.exits == 1 and not gate.held
        gate.blocked = True
        with pytest.raises(PermissionError, match="FENCED"):
            await wrapped.complete(None)
    assert provider._index == 0
