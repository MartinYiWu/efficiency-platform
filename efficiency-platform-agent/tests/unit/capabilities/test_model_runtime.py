"""模型 Runtime 的 RED/GREEN 契约测试。"""

import asyncio

import pytest

from efficiency_platform_agent.capabilities.model.runtime import (
    ModelBudgetContext,
    ModelLeaseContext,
    ModelRuntime,
)
from efficiency_platform_agent.core.budget import BudgetGuard, RemainingBudget
from efficiency_platform_agent.core.budget_execution import (
    BudgetExecutionBinding,
    bind_budget_execution,
)
from efficiency_platform_agent.core.budget_lease import (
    BudgetLimits,
    BudgetScope,
    InMemoryBudgetLeaseRepository,
)
from efficiency_platform_agent.core.diagnostics import DiagnosticRecord
from efficiency_platform_agent.core.model import ModelDemand, ModelTier
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    ExtensionDescriptor,
    JsonObject,
    ProviderError,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
    ProviderStreamChunk,
    ProviderUsage,
)
from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
from efficiency_platform_agent.providers.llm.registry import ModelProviderRegistry
from efficiency_platform_agent.routing.model_router import ModelPolicyRouter


def request() -> ProviderRequest:
    """构造不包含受控 logical_model 的请求。"""
    return ProviderRequest(
        "s2.provider/1", (ProviderMessage("user", "hi"),), JsonObject(), 100
    )


def result(text: str) -> ProviderResult:
    """构造带明确 Provider Usage 的成功结果。"""
    return ProviderResult(
        "s2.provider/1",
        ProviderMessage("assistant", text),
        ProviderUsage(2, 3, 0, 0, 5),
    )


@pytest.mark.asyncio
async def test_runtime_uses_task_local_live_acceptance_lease_when_not_explicit() -> None:
    registry = ModelProviderRegistry()
    registry.register(
        "fake_strong", FakeModelProvider("fake_strong", [result("bound")])
    )
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

    with bind_budget_execution(binding):
        execution = await ModelRuntime(ModelPolicyRouter(), registry).complete(
            ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10),
            request(),
            remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1_000),
        )

    snapshot = await repository.snapshot(scope)
    assert execution.result.message is not None
    assert execution.result.message.content == "bound"
    assert snapshot.used.calls == 1
    assert snapshot.used.cost_microunits == 5
    assert binding.version == snapshot.version


class _DiagnosticRecorder:
    """收集白名单诊断记录，供断言调用边界使用。"""

    def __init__(self) -> None:
        self.records: list[DiagnosticRecord] = []

    def record(self, record: DiagnosticRecord) -> None:
        self.records.append(record)


class _ExplodingStreamingProvider:
    """在流迭代阶段抛出普通异常的受控 Provider。"""

    def __init__(self) -> None:
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

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        """该测试 Provider 只允许经流式入口调用。"""

        del request
        raise AssertionError("不应调用 complete")

    async def stream(self, request: ProviderRequest):
        """模拟 Provider 在读取首个流事件前发生异常。"""

        del request
        if False:
            yield ProviderStreamChunk()
        raise RuntimeError("不得进入诊断日志的异常正文")


class _TerminalCompletingProvider(FakeModelProvider):
    def __init__(
        self,
        repository: InMemoryBudgetLeaseRepository,
        scope: BudgetScope,
    ) -> None:
        super().__init__("fake_strong", [result("late")])
        self._repository = repository
        self._scope = scope

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        await self._repository.mark_scope_terminal(self._scope, "cancelled")
        return await super().complete(request)


@pytest.mark.asyncio
async def test_runtime_degrades_once_and_accumulates_provider_usage() -> None:
    """临时错误最多切换一次，并且只累计 Provider 明确返回的 Usage。"""
    registry = ModelProviderRegistry()
    registry.register(
        "fake_strong",
        FakeModelProvider(
            "fake_strong",
            [
                ProviderResult(
                    "s2.provider/1",
                    None,
                    ProviderUsage(1, 0, 0, 0, 1),
                    ProviderError("DOWN", "server_error", True, "temporary"),
                )
            ],
        ),
    )
    registry.register(
        "fake_balanced", FakeModelProvider("fake_balanced", [result("ok")])
    )
    runtime = ModelRuntime(ModelPolicyRouter(), registry)
    execution = await runtime.complete(
        ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10),
        request(),
        remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1000),
    )
    assert execution.result.message is not None
    assert execution.result.message.content == "ok"
    assert execution.degraded is True
    assert len(execution.attempts) == 2
    assert execution.usage.input_tokens == 3
    assert execution.usage.output_tokens == 3
    assert execution.usage.estimated is True


@pytest.mark.asyncio
async def test_runtime_records_failed_candidate_fallback_and_success_without_request_body() -> (
    None
):
    """候选调用诊断只记录事实，不记录用户消息或 options。"""

    recorder = _DiagnosticRecorder()
    registry = ModelProviderRegistry()
    registry.register(
        "fake_strong",
        FakeModelProvider(
            "fake_strong",
            [
                ProviderResult(
                    "s2.provider/1",
                    None,
                    ProviderUsage(1, 0, 0, 0, 1),
                    ProviderError("DOWN", "server_error", True, "synthetic secret"),
                )
            ],
        ),
    )
    registry.register(
        "fake_balanced", FakeModelProvider("fake_balanced", [result("output body")])
    )
    sensitive_message = "user body must stay private"
    request_with_sensitive_message = ProviderRequest(
        "s2.provider/1",
        (ProviderMessage("user", sensitive_message),),
        JsonObject((("authorization", "synthetic-secret"),)),
        100,
    )

    execution = await ModelRuntime(
        ModelPolicyRouter(), registry, diagnostic_recorder=recorder
    ).complete(
        ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10),
        request_with_sensitive_message,
        remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1000),
    )

    assert execution.result.message is not None
    assert [record.event_name for record in recorder.records] == [
        "model_invocation_started",
        "model_invocation_failed",
        "model_fallback_selected",
        "model_invocation_started",
        "model_invocation_succeeded",
    ]
    failed = recorder.records[1]
    succeeded = recorder.records[-1]
    assert failed.error_code == "DOWN"
    assert failed.attempt == 1
    assert recorder.records[0].provider_call_id == failed.provider_call_id
    assert failed.provider_call_id is not None
    assert recorder.records[3].provider_call_id == succeeded.provider_call_id
    assert succeeded.provider_call_id is not None
    assert failed.provider_call_id != succeeded.provider_call_id
    assert succeeded.input_tokens == 2
    assert succeeded.output_tokens == 3
    assert succeeded.duration_ms is not None
    assert succeeded.duration_ms >= 0
    diagnostic_text = repr(recorder.records)
    assert sensitive_message not in diagnostic_text
    assert "synthetic-secret" not in diagnostic_text
    assert "output body" not in diagnostic_text


@pytest.mark.asyncio
async def test_stream_complete_normalizes_and_records_unhandled_provider_exception() -> None:
    """流式普通异常须归一化并记录，不能只留下 started 后原样上抛。"""

    recorder = _DiagnosticRecorder()
    registry = ModelProviderRegistry()
    registry.register("fake_strong", _ExplodingStreamingProvider())
    execution = await ModelRuntime(
        ModelPolicyRouter(), registry, diagnostic_recorder=recorder
    ).stream_complete(
        ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10),
        request(),
        remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1000),
        on_delta=lambda _delta: None,
    )

    assert execution.result.error is not None
    assert execution.result.error.code == "PROVIDER_FAILURE"
    assert [record.event_name for record in recorder.records] == [
        "model_invocation_started",
        "model_invocation_failed",
    ]
    failed = recorder.records[-1]
    assert failed.error_type == "RuntimeError"
    assert failed.error_location is not None
    assert recorder.records[0].provider_call_id == failed.provider_call_id
    assert failed.provider_call_id is not None
    assert "不得进入诊断日志的异常正文" not in repr(recorder.records)


@pytest.mark.asyncio
async def test_stream_complete_records_provider_resolution_failure() -> None:
    """候选已选中但 Provider 未注册时也必须形成完整失败诊断。"""

    recorder = _DiagnosticRecorder()
    execution = await ModelRuntime(
        ModelPolicyRouter(),
        ModelProviderRegistry(),
        diagnostic_recorder=recorder,
    ).stream_complete(
        ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10),
        request(),
        remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1000),
        on_delta=lambda _delta: None,
    )

    assert execution.result.error is not None
    assert execution.result.error.code == "PROVIDER_FAILURE"
    assert [record.event_name for record in recorder.records] == [
        "model_invocation_failed"
    ]
    assert recorder.records[-1].error_type == "KeyError"


@pytest.mark.asyncio
async def test_non_retryable_error_does_not_degrade_and_script_exhaustion_is_stable() -> (
    None
):
    """认证、非法请求和 Schema 错误不得切换候选。"""
    registry = ModelProviderRegistry()
    registry.register(
        "fake_strong",
        FakeModelProvider(
            "fake_strong",
            [
                ProviderResult(
                    "s2.provider/1",
                    None,
                    ProviderUsage(0, 0, 0, 0, 0),
                    ProviderError("AUTH", "authentication", False, "denied"),
                )
            ],
        ),
    )
    registry.register(
        "fake_balanced", FakeModelProvider("fake_balanced", [result("must-not-run")])
    )
    execution = await ModelRuntime(ModelPolicyRouter(), registry).complete(
        ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10),
        request(),
        remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1000),
    )
    assert execution.result.error is not None
    assert execution.result.error.category == "authentication"
    assert len(execution.attempts) == 1


@pytest.mark.asyncio
async def test_unknown_provider_exception_is_safe_and_does_not_degrade() -> None:
    """Provider 未知异常必须安全归一化为不可重试错误。"""

    class ExplodingProvider(FakeModelProvider):
        async def complete(self, request: ProviderRequest) -> ProviderResult:
            raise ValueError("vendor internals must not leak")

    registry = ModelProviderRegistry()
    registry.register("fake_strong", ExplodingProvider("fake_strong", []))
    registry.register(
        "fake_balanced", FakeModelProvider("fake_balanced", [result("must-not-run")])
    )

    execution = await ModelRuntime(ModelPolicyRouter(), registry).complete(
        ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10),
        request(),
        remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1000),
    )

    assert execution.result.message is None
    assert execution.result.error is not None
    assert execution.result.error.code == "PROVIDER_FAILURE"
    assert execution.result.error.category == "provider"
    assert execution.result.error.retryable is False
    assert len(execution.attempts) == 1


@pytest.mark.asyncio
async def test_unknown_retryable_provider_error_code_does_not_degrade() -> None:
    """仅白名单 code/category/retryable 组合允许切换候选。"""
    registry = ModelProviderRegistry()
    registry.register(
        "fake_strong",
        FakeModelProvider(
            "fake_strong",
            [
                ProviderResult(
                    "s2.provider/1",
                    None,
                    ProviderUsage(0, 0, 0, 0, 0),
                    ProviderError("UNKNOWN_TRANSIENT", "connection", True, "temporary"),
                )
            ],
        ),
    )
    registry.register(
        "fake_balanced", FakeModelProvider("fake_balanced", [result("must-not-run")])
    )

    execution = await ModelRuntime(ModelPolicyRouter(), registry).complete(
        ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10),
        request(),
        remaining_budget=RemainingBudget(10, 10, 100, 100, 100, 1000),
    )

    assert execution.result.error is not None
    assert execution.result.error.code == "UNKNOWN_TRANSIENT"
    assert len(execution.attempts) == 1


@pytest.mark.asyncio
async def test_iteration_budget_is_consumed_before_a_second_candidate_without_guard() -> (
    None
):
    """未注入 BudgetGuard 时每次候选尝试也必须消耗 iteration 额度。"""
    registry = ModelProviderRegistry()
    registry.register(
        "fake_strong",
        FakeModelProvider(
            "fake_strong",
            [
                ProviderResult(
                    "s2.provider/1",
                    None,
                    ProviderUsage(0, 0, 0, 0, 0),
                    ProviderError("DOWN", "server_error", True, "temporary"),
                )
            ],
        ),
    )
    balanced = FakeModelProvider("fake_balanced", [result("must-not-run")])
    registry.register("fake_balanced", balanced)

    execution = await ModelRuntime(ModelPolicyRouter(), registry).complete(
        ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10),
        request(),
        remaining_budget=RemainingBudget(1, 10, 100, 100, 100, 1000),
    )

    assert execution.result.message is None
    assert execution.result.error is not None
    assert execution.result.error.code == "BUDGET_EXHAUSTED"
    assert len(execution.attempts) == 1
    assert balanced._index == 0


@pytest.mark.asyncio
async def test_concurrent_model_calls_keep_budget_contexts_isolated() -> None:
    registry = ModelProviderRegistry()
    registry.register(
        "fake_strong",
        FakeModelProvider("fake_strong", [result("one"), result("two")]),
    )
    runtime = ModelRuntime(ModelPolicyRouter(), registry, clock=lambda: 1_001)
    budget = ExecutionBudget(2, 0, 100, 100, 10_000, 100)
    first_guard = BudgetGuard()
    second_guard = BudgetGuard()
    first_context = ModelBudgetContext(
        first_guard,
        budget,
        first_guard.start(budget, now_epoch_ms=1_000),
    )
    second_context = ModelBudgetContext(
        second_guard,
        budget,
        second_guard.start(budget, now_epoch_ms=1_000),
    )
    model_demand = ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10)

    async def invoke(context: ModelBudgetContext):
        return await runtime.complete(
            model_demand,
            request(),
            remaining_budget=RemainingBudget(2, 0, 100, 100, 100, 1_000),
            budget_context=context,
        )

    await asyncio.gather(invoke(first_context), invoke(second_context))
    assert first_context.state.consumed.iterations == 1
    assert second_context.state.consumed.iterations == 1
    assert first_context.state.consumed.input_tokens == 2
    assert second_context.state.consumed.input_tokens == 2


@pytest.mark.asyncio
async def test_parent_lease_rejection_prevents_model_dispatch() -> None:
    registry = ModelProviderRegistry()
    provider = FakeModelProvider("fake_strong", [result("must-not-run")])
    registry.register("fake_strong", provider)
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=0, max_bytes=0, max_cost_microunits=100)
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "model")
    execution = await ModelRuntime(ModelPolicyRouter(), registry).complete(
        ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10),
        request(),
        remaining_budget=RemainingBudget(2, 0, 100, 100, 100, 1_000),
        lease_context=ModelLeaseContext(repository, scope, "model-call", 0),
    )
    assert execution.result.error is not None
    assert execution.result.error.code == "BUDGET_EXHAUSTED"
    assert provider._index == 0
    assert repository.dispatched_invocation_count == 0


@pytest.mark.asyncio
async def test_successful_model_attempt_uses_parent_lease_once() -> None:
    registry = ModelProviderRegistry()
    provider = FakeModelProvider("fake_strong", [result("ok")])
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
    lease_context = ModelLeaseContext(repository, scope, "model-call", 0)
    execution = await ModelRuntime(ModelPolicyRouter(), registry).complete(
        ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10),
        request(),
        remaining_budget=RemainingBudget(2, 0, 100, 100, 100, 1_000),
        lease_context=lease_context,
    )
    snapshot = await repository.snapshot(scope)
    assert execution.result.message is not None
    assert snapshot.used.calls == 1
    assert snapshot.used.input_tokens == 2
    assert snapshot.used.output_tokens == 3
    assert snapshot.used.cost_microunits == 5
    assert snapshot.reserved.calls == 0
    assert lease_context.version == snapshot.version


@pytest.mark.asyncio
async def test_model_lease_is_the_only_budget_path() -> None:
    registry = ModelProviderRegistry()
    registry.register("fake_strong", FakeModelProvider("fake_strong", [result("ok")]))
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(max_calls=1, max_bytes=0, max_cost_microunits=100)
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "model")
    budget = ExecutionBudget(2, 0, 100, 100, 10_000, 100)
    guard = BudgetGuard()
    context = ModelBudgetContext(
        guard,
        budget,
        guard.start(budget, now_epoch_ms=1_000),
    )
    with pytest.raises(ValueError, match="唯一预算计账路径"):
        await ModelRuntime(ModelPolicyRouter(), registry).complete(
            ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10),
            request(),
            remaining_budget=RemainingBudget(2, 0, 100, 100, 100, 1_000),
            budget_context=context,
            lease_context=ModelLeaseContext(repository, scope, "model-call", 0),
        )


@pytest.mark.asyncio
async def test_late_model_success_is_audit_only_and_not_delivered() -> None:
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
    registry = ModelProviderRegistry()
    registry.register(
        "fake_strong", _TerminalCompletingProvider(repository, scope)
    )
    execution = await ModelRuntime(ModelPolicyRouter(), registry).complete(
        ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10),
        request(),
        remaining_budget=RemainingBudget(2, 0, 100, 100, 100, 1_000),
        lease_context=ModelLeaseContext(repository, scope, "model-call", 0),
    )
    assert execution.result.message is None
    assert execution.result.error is not None
    assert execution.result.error.code == "CANCELLED"
    assert execution.usage.output_tokens == 3
    assert repository.audit_records[-1].delivery_allowed is False


@pytest.mark.asyncio
async def test_concurrent_parent_model_leases_retry_fresh_cas_version() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=2,
            max_bytes=0,
            max_cost_microunits=200,
            max_input_tokens=100,
            max_output_tokens=100,
        )
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "model")
    registry = ModelProviderRegistry()
    provider = FakeModelProvider("fake_strong", [result("one"), result("two")])
    registry.register("fake_strong", provider)
    runtime = ModelRuntime(ModelPolicyRouter(), registry)
    model_demand = ModelDemand(
        "s2.model/1", ModelTier.STRONG, False, False, 2, 10
    )

    async def invoke(prefix: str):
        return await runtime.complete(
            model_demand,
            request(),
            remaining_budget=RemainingBudget(2, 0, 100, 100, 100, 1_000),
            lease_context=ModelLeaseContext(repository, scope, prefix, 0),
        )

    first, second = await asyncio.gather(invoke("first"), invoke("second"))
    snapshot = await repository.snapshot(scope)
    assert first.result.error is None
    assert second.result.error is None
    assert provider._index == 2
    assert snapshot.used.calls == 2
    assert snapshot.reserved.calls == 0


@pytest.mark.asyncio
async def test_constructor_budget_accumulates_across_model_calls() -> None:
    registry = ModelProviderRegistry()
    provider = FakeModelProvider("fake_strong", [result("one"), result("must-not-run")])
    registry.register("fake_strong", provider)
    budget = ExecutionBudget(1, 0, 100, 100, 10_000, 100)
    guard = BudgetGuard()
    runtime = ModelRuntime(
        ModelPolicyRouter(),
        registry,
        budget_guard=guard,
        budget=budget,
        budget_state=guard.start(budget, now_epoch_ms=1_000),
        clock=lambda: 1_001,
    )
    model_demand = ModelDemand(
        "s2.model/1", ModelTier.STRONG, False, False, 2, 10
    )

    first = await runtime.complete(
        model_demand,
        request(),
        remaining_budget=RemainingBudget(2, 0, 100, 100, 100, 1_000),
    )
    second = await runtime.complete(
        model_demand,
        request(),
        remaining_budget=RemainingBudget(2, 0, 100, 100, 100, 1_000),
    )
    assert first.result.error is None
    assert second.result.error is not None
    assert second.result.error.code == "BUDGET_EXHAUSTED"
    assert provider._index == 1
    assert runtime.budget_state is not None
    assert runtime.budget_state.consumed.iterations == 1


@pytest.mark.asyncio
async def test_model_overrun_error_preserves_observed_usage() -> None:
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
    registry = ModelProviderRegistry()
    registry.register("fake_strong", FakeModelProvider("fake_strong", [result("late")]))
    execution = await ModelRuntime(ModelPolicyRouter(), registry).complete(
        ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 2, 10),
        request(),
        remaining_budget=RemainingBudget(2, 0, 100, 100, 100, 1_000),
        lease_context=ModelLeaseContext(
            repository,
            scope,
            "model-overrun",
            0,
            reserve_cost_microunits=0,
        ),
    )
    snapshot = await repository.snapshot(scope)
    assert execution.result.error is not None
    assert execution.result.error.code == "BUDGET_EXHAUSTED"
    assert execution.result.usage.cost_microunits == 5
    assert execution.usage.cost_microunits == 5
    assert snapshot.used.cost_microunits == 5
    assert repository.audit_records[-1].actual.cost_microunits == 5
