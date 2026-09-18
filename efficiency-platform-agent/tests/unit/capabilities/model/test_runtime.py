"""模型 Runtime 实时流式执行的契约测试。"""

from __future__ import annotations

import asyncio

import pytest

from efficiency_platform_agent.capabilities.model.runtime import (
    ModelBudgetContext,
    ModelLeaseContext,
    ModelRuntime,
)
from efficiency_platform_agent.core.budget import (
    BudgetCharge,
    BudgetGuard,
    BudgetState,
    RemainingBudget,
)
from efficiency_platform_agent.core.budget_execution import (
    BudgetExecutionBinding,
    bind_budget_execution,
)
from efficiency_platform_agent.core.budget_lease import (
    BudgetLimits,
    BudgetScope,
    InMemoryBudgetLeaseRepository,
)
from efficiency_platform_agent.core.model import ModelDemand, ModelTier
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    ExtensionDescriptor,
    JsonObject,
    ProviderError,
    ProviderMessage,
    ProviderRequest,
    ProviderStreamChunk,
    ProviderUsage,
)
from efficiency_platform_agent.providers.llm.registry import ModelProviderRegistry
from efficiency_platform_agent.routing.model_router import ModelPolicyRouter


def request() -> ProviderRequest:
    """构造不包含受控 logical_model 的请求。"""
    return ProviderRequest(
        "s2.provider/1", (ProviderMessage("user", "hi"),), JsonObject(), 1_000
    )


def demand() -> ModelDemand:
    """构造选择 strong 候选的模型需求。"""
    return ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10)


class BlockingStreamingProvider:
    """首个增量后等待测试显式放行的流式 Provider。"""

    def __init__(self, first_delta_delivered: asyncio.Event, release: asyncio.Event) -> None:
        self.first_delta_delivered = first_delta_delivered
        self.release = release
        self.finished = False
        self.descriptor = ExtensionDescriptor(
            name="fake_strong",
            semantic_version="1.0.0",
            input_schema_version="s2.provider/1",
            output_schema_version="s2.provider/1",
            permissions=frozenset(),
            budget=ExecutionBudget(1, 0, 1_000, 1_000, 60_000, 1_000_000),
            termination_conditions=frozenset({"provider_returned"}),
            checkpoint_version="s2.provider/1",
        )

    async def complete(self, request: ProviderRequest):
        """该测试 Provider 只允许经流式入口调用。"""
        raise AssertionError("不应调用 complete")

    async def stream(self, request: ProviderRequest):
        """先交付首个增量，再等待测试放行结束。"""
        yield ProviderStreamChunk("你", ProviderUsage(2, 1, 0, 0, 3))
        self.first_delta_delivered.set()
        await self.release.wait()
        self.finished = True
        yield ProviderStreamChunk("好", ProviderUsage(2, 2, 0, 0, 5), "stop")


class ScriptedStreamingProvider:
    """按每次调用的脚本顺序交付流式 chunk。"""

    def __init__(self, provider_id: str, streams: tuple[tuple[ProviderStreamChunk, ...], ...]) -> None:
        self.provider_id = provider_id
        self.streams = streams
        self.calls = 0
        self.descriptor = ExtensionDescriptor(
            name=provider_id,
            semantic_version="1.0.0",
            input_schema_version="s2.provider/1",
            output_schema_version="s2.provider/1",
            permissions=frozenset(),
            budget=ExecutionBudget(1, 0, 1_000, 1_000, 60_000, 1_000_000),
            termination_conditions=frozenset({"provider_returned"}),
            checkpoint_version="s2.provider/1",
        )

    async def complete(self, request: ProviderRequest):
        """该测试 Provider 只允许经流式入口调用。"""
        raise AssertionError("不应调用 complete")

    async def stream(self, request: ProviderRequest):
        """消费一次流脚本。"""
        script = self.streams[self.calls]
        self.calls += 1
        for chunk in script:
            yield chunk


class TerminalStreamingProvider(ScriptedStreamingProvider):
    """在返回正文前把对应 Run 标记为取消终态。"""

    def __init__(
        self,
        repository: InMemoryBudgetLeaseRepository,
        scope: BudgetScope,
    ) -> None:
        super().__init__(
            "fake_strong",
            ((ProviderStreamChunk("late-secret", ProviderUsage(2, 1, 0, 0, 0)),),),
        )
        self.repository = repository
        self.scope = scope

    async def stream(self, request: ProviderRequest):
        await self.repository.mark_scope_terminal(self.scope, "cancelled")
        async for chunk in super().stream(request):
            yield chunk


class MutableCancellationSignal:
    """允许测试在首个可见 delta 后请求取消。"""

    def __init__(self) -> None:
        self.requested = False

    def wait_requested(self) -> bool:
        """返回当前取消状态。"""
        return self.requested


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["stream", "stream_complete"])
async def test_stream_entrypoints_inherit_task_local_acceptance_lease(
    entrypoint: str,
) -> None:
    provider = ScriptedStreamingProvider(
        "fake_strong",
        (
            (
                ProviderStreamChunk("你", ProviderUsage(2, 1, 0, 0, 3)),
                ProviderStreamChunk(
                    "好", ProviderUsage(2, 2, 0, 0, 5), "stop"
                ),
            ),
        ),
    )
    registry = ModelProviderRegistry()
    registry.register("fake_strong", provider)
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=2,
            max_bytes=0,
            max_cost_microunits=100,
            max_input_tokens=100,
            max_output_tokens=100,
        )
    )
    scope = BudgetScope("tenant-1", "acceptance-1", "live_acceptance", "all")
    binding = BudgetExecutionBinding(
        repository,
        scope,
        "lease-live-1",
        "a" * 64,
    )
    runtime = ModelRuntime(ModelPolicyRouter(), registry)
    deltas: list[str] = []

    with bind_budget_execution(binding):
        if entrypoint == "stream":
            chunks = [
                chunk
                async for chunk in runtime.stream(
                    demand(),
                    request(),
                    remaining_budget=RemainingBudget(
                        10, 10, 100, 100, 100, 1_000
                    ),
                )
            ]
            assert "".join(chunk.delta or "" for chunk in chunks) == "你好"
        else:
            execution = await runtime.stream_complete(
                demand(),
                request(),
                remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1_000),
                on_delta=deltas.append,
            )
            assert execution.result.message is not None
            assert deltas == ["你", "好"]

    snapshot = await repository.snapshot(scope)
    assert snapshot.used.calls == 1
    assert snapshot.used.cost_microunits == 5
    assert binding.version == snapshot.version


@pytest.mark.asyncio
async def test_stream_complete_settles_parent_lease_once() -> None:
    provider = ScriptedStreamingProvider(
        "fake_strong",
        (
            (
                ProviderStreamChunk("你", ProviderUsage(2, 1, 0, 0, 3)),
                ProviderStreamChunk(
                    "好", ProviderUsage(2, 2, 0, 0, 5), "stop"
                ),
            ),
        ),
    )
    registry = ModelProviderRegistry()
    registry.register("fake_strong", provider)
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=1,
            max_bytes=0,
            max_cost_microunits=100,
            max_input_tokens=100,
            max_output_tokens=100,
        )
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "model")
    context = ModelLeaseContext(repository, scope, "stream-model", 0)
    received: list[str] = []

    execution = await ModelRuntime(
        ModelPolicyRouter(), registry
    ).stream_complete(
        demand(),
        request(),
        remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1_000),
        on_delta=received.append,
        lease_context=context,
    )

    snapshot = await repository.snapshot(scope)
    assert execution.result.message is not None
    assert received == ["你", "好"]
    assert provider.calls == 1
    assert snapshot.used.calls == 1
    assert snapshot.used.input_tokens == 2
    assert snapshot.used.output_tokens == 2
    assert snapshot.used.cost_microunits == 5
    assert snapshot.reserved.calls == 0


@pytest.mark.asyncio
async def test_stream_parent_lease_rejection_prevents_provider_dispatch() -> None:
    provider = ScriptedStreamingProvider(
        "fake_strong",
        ((ProviderStreamChunk("不应调用", ProviderUsage(1, 1, 0, 0, 0)),),),
    )
    registry = ModelProviderRegistry()
    registry.register("fake_strong", provider)
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=0, max_bytes=0, max_cost_microunits=0)
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "model")

    chunks = [
        chunk
        async for chunk in ModelRuntime(ModelPolicyRouter(), registry).stream(
            demand(),
            request(),
            remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1_000),
            lease_context=ModelLeaseContext(
                repository, scope, "stream-model", 0
            ),
        )
    ]

    assert len(chunks) == 1
    assert chunks[0].error is not None
    assert chunks[0].error.code == "BUDGET_EXHAUSTED"
    assert provider.calls == 0
    assert repository.dispatched_invocation_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["stream", "stream_complete"])
async def test_leased_stream_never_delivers_before_failed_settlement(
    entrypoint: str,
) -> None:
    provider = ScriptedStreamingProvider(
        "fake_strong",
        ((ProviderStreamChunk("secret", ProviderUsage(2, 1, 0, 0, 5)),),),
    )
    registry = ModelProviderRegistry()
    registry.register("fake_strong", provider)
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=1,
            max_bytes=0,
            max_cost_microunits=0,
            max_input_tokens=100,
            max_output_tokens=100,
        )
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "model")
    context = ModelLeaseContext(
        repository,
        scope,
        f"failed-{entrypoint}",
        0,
        reserve_cost_microunits=0,
    )
    runtime = ModelRuntime(ModelPolicyRouter(), registry)
    emitted: list[str] = []

    if entrypoint == "stream":
        chunks = [
            chunk
            async for chunk in runtime.stream(
                demand(),
                request(),
                remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1_000),
                lease_context=context,
            )
        ]
        emitted.extend(chunk.delta for chunk in chunks if chunk.delta)
        assert chunks[-1].error is not None
        assert chunks[-1].error.code == "BUDGET_EXHAUSTED"
    else:
        execution = await runtime.stream_complete(
            demand(),
            request(),
            remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1_000),
            on_delta=emitted.append,
            lease_context=context,
        )
        assert execution.result.error is not None
        assert execution.result.error.code == "BUDGET_EXHAUSTED"

    snapshot = await repository.snapshot(scope)
    assert emitted == []
    assert provider.calls == 1
    assert snapshot.reserved.calls == 0
    assert snapshot.used.calls == 1
    assert snapshot.used.cost_microunits == 5
    assert repository.audit_records[-1].actual.cost_microunits == 5
    assert repository.audit_records[-1].over_limit is True
    assert repository.audit_records[-1].outcome == "success"
    assert repository.audit_records[-1].delivery_allowed is False


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["stream", "stream_complete"])
async def test_terminal_leased_stream_never_delivers_late_success(
    entrypoint: str,
) -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=1,
            max_bytes=0,
            max_cost_microunits=0,
            max_input_tokens=100,
            max_output_tokens=100,
        )
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "model")
    provider = TerminalStreamingProvider(repository, scope)
    registry = ModelProviderRegistry()
    registry.register("fake_strong", provider)
    runtime = ModelRuntime(ModelPolicyRouter(), registry)
    context = ModelLeaseContext(
        repository,
        scope,
        f"terminal-{entrypoint}",
        0,
        reserve_cost_microunits=0,
    )
    emitted: list[str] = []

    if entrypoint == "stream":
        chunks = [
            chunk
            async for chunk in runtime.stream(
                demand(),
                request(),
                remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1_000),
                lease_context=context,
            )
        ]
        emitted.extend(chunk.delta for chunk in chunks if chunk.delta)
        assert chunks[-1].error is not None
        assert chunks[-1].error.code == "CANCELLED"
    else:
        execution = await runtime.stream_complete(
            demand(),
            request(),
            remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1_000),
            on_delta=emitted.append,
            lease_context=context,
        )
        assert execution.result.error is not None
        assert execution.result.error.code == "CANCELLED"

    assert emitted == []
    assert repository.audit_records[-1].delivery_allowed is False


@pytest.mark.asyncio
async def test_stream_complete_delivers_first_delta_before_returning_full_result() -> None:
    """首个 delta 必须在 Provider 完成前对调用方可见，结束后返回完整结果。"""
    first_delta_delivered = asyncio.Event()
    release = asyncio.Event()
    provider = BlockingStreamingProvider(first_delta_delivered, release)
    registry = ModelProviderRegistry()
    registry.register("fake_strong", provider)
    received: list[str] = []

    async def deliver(delta: str) -> None:
        """记录调用方实时收到的正文增量。"""
        received.append(delta)

    task = asyncio.create_task(
        ModelRuntime(ModelPolicyRouter(), registry).stream_complete(
            demand(),
            request(),
            remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1_000),
            on_delta=deliver,
        )
    )

    await first_delta_delivered.wait()

    assert received == ["你"]
    assert provider.finished is False
    assert task.done() is False

    release.set()
    execution = await task

    assert execution.result.message is not None
    assert execution.result.message.content == "你好"
    assert execution.usage.input_tokens == 2
    assert execution.usage.output_tokens == 2
    assert execution.usage.cost_microunits == 5
    assert len(execution.attempts) == 1
    assert execution.degraded is False


@pytest.mark.asyncio
async def test_stream_complete_degrades_before_first_delta_and_uses_candidate_usage_maximum() -> None:
    """首个可见 delta 前的临时失败可降级，Usage 只取每候选快照最大值。"""
    strong = ScriptedStreamingProvider(
        "fake_strong",
        (
            (
                ProviderStreamChunk(
                    error=ProviderError("DOWN", "server_error", True, "temporary"),
                    usage=ProviderUsage(1, 0, 0, 0, 1),
                ),
            ),
        ),
    )
    balanced = ScriptedStreamingProvider(
        "fake_balanced",
        (
            (
                ProviderStreamChunk("补", ProviderUsage(3, 1, 0, 0, 3)),
                ProviderStreamChunk("全", ProviderUsage(3, 2, 0, 0, 5), "stop"),
            ),
        ),
    )
    registry = ModelProviderRegistry()
    registry.register("fake_strong", strong)
    registry.register("fake_balanced", balanced)
    received: list[str] = []

    execution = await ModelRuntime(ModelPolicyRouter(), registry).stream_complete(
        demand(),
        request(),
        remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1_000),
        on_delta=received.append,
    )

    assert received == ["补", "全"]
    assert execution.result.message is not None
    assert execution.result.message.content == "补全"
    assert execution.degraded is True
    assert len(execution.attempts) == 2
    assert execution.usage.input_tokens == 4
    assert execution.usage.output_tokens == 2
    assert execution.usage.cost_microunits == 6


@pytest.mark.asyncio
async def test_stream_complete_stops_delivery_and_fallback_after_cancellation() -> None:
    """首个可见 delta 后取消，后续 chunk 和候选均不得再交付或调用。"""
    strong = ScriptedStreamingProvider(
        "fake_strong",
        (
            (
                ProviderStreamChunk("可见", ProviderUsage(1, 1, 0, 0, 1)),
                ProviderStreamChunk("不可见", ProviderUsage(1, 2, 0, 0, 2)),
                ProviderStreamChunk(
                    error=ProviderError("DOWN", "server_error", True, "temporary")
                ),
            ),
        ),
    )
    balanced = ScriptedStreamingProvider(
        "fake_balanced", ((ProviderStreamChunk("不得调用"),),)
    )
    registry = ModelProviderRegistry()
    registry.register("fake_strong", strong)
    registry.register("fake_balanced", balanced)
    cancellation = MutableCancellationSignal()
    received: list[str] = []

    def deliver(delta: str) -> None:
        """在首个正文增量送达后请求取消。"""
        received.append(delta)
        cancellation.requested = True

    execution = await ModelRuntime(
        ModelPolicyRouter(), registry, cancellation_signal=cancellation
    ).stream_complete(
        demand(),
        request(),
        remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1_000),
        on_delta=deliver,
    )

    assert received == ["可见"]
    assert execution.result.error is not None
    assert execution.result.error.code == "CANCELLED"
    assert len(execution.attempts) == 1
    assert balanced.calls == 0


@pytest.mark.asyncio
async def test_stream_complete_returns_cancelled_when_callback_cancels_final_delta() -> None:
    """最后一个 delta 的回调触发取消时，不得将该次调用误判为成功。"""
    strong = ScriptedStreamingProvider(
        "fake_strong",
        ((ProviderStreamChunk("最后", ProviderUsage(1, 1, 0, 0, 1), "stop"),),),
    )
    registry = ModelProviderRegistry()
    registry.register("fake_strong", strong)
    cancellation = MutableCancellationSignal()

    def deliver(delta: str) -> None:
        """在最终正文送达后立即请求取消。"""
        cancellation.requested = True

    execution = await ModelRuntime(
        ModelPolicyRouter(), registry, cancellation_signal=cancellation
    ).stream_complete(
        demand(),
        request(),
        remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1_000),
        on_delta=deliver,
    )

    assert execution.result.error is not None
    assert execution.result.error.code == "CANCELLED"


@pytest.mark.asyncio
async def test_stream_and_stream_complete_both_record_error_chunk_usage_snapshot() -> None:
    """携带非零 Usage 的错误 chunk 必须在两个流式入口中采用同一最大快照。"""
    error_chunk = ProviderStreamChunk(
        error=ProviderError("AUTH", "authentication", False, "denied"),
        usage=ProviderUsage(7, 3, 0, 0, 11),
    )
    budget = ExecutionBudget(10, 0, 100, 100, 1_000, 100)
    guard = BudgetGuard()
    state = BudgetState(BudgetCharge(), 1, 10_001)

    class FixedClock:
        """固定预算时钟，避免测试受真实时间影响。"""

        def now_epoch_ms(self) -> int:
            """返回预算仍有效的固定时刻。"""
            return 1

    def runtime_for(provider: ScriptedStreamingProvider, budget_state: BudgetState):
        """构造拥有独立预算状态的流式 Runtime。"""
        registry = ModelProviderRegistry()
        registry.register("fake_strong", provider)
        return (
            ModelRuntime(
                ModelPolicyRouter(),
                registry,
                clock=FixedClock(),
                monotonic_clock=lambda: 0.0,
            ),
            ModelBudgetContext(guard, budget, budget_state),
        )

    stream_runtime, stream_context = runtime_for(
        ScriptedStreamingProvider("fake_strong", ((error_chunk,),)), state
    )
    chunks = [
        chunk
        async for chunk in stream_runtime.stream(
            demand(),
            request(),
            remaining_budget=RemainingBudget(10, 0, 100, 100, 100, 1_000),
            budget_context=stream_context,
        )
    ]
    complete_runtime, complete_context = runtime_for(
        ScriptedStreamingProvider("fake_strong", ((error_chunk,),)),
        BudgetState(BudgetCharge(), 1, 10_001),
    )
    execution = await complete_runtime.stream_complete(
        demand(),
        request(),
        remaining_budget=RemainingBudget(10, 0, 100, 100, 100, 1_000),
        on_delta=lambda _delta: None,
        budget_context=complete_context,
    )

    assert chunks[0].error is not None
    assert stream_context.state.consumed.input_tokens == 7
    assert stream_context.state.consumed.output_tokens == 3
    assert stream_context.state.consumed.cost_microunits == 11
    assert execution.usage.input_tokens == 7
    assert execution.usage.output_tokens == 3
    assert execution.usage.cost_microunits == 11
