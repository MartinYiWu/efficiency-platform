"""S2 离线测试组合根，只装配 Fake 与进程内实现。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from efficiency_platform_agent.context.builder import ContextBuilder
from efficiency_platform_agent.core.budget import BudgetGuard
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.orchestration.cancellation import (
    InMemoryCancellationSignal,
)
from efficiency_platform_agent.orchestration.registry import build_default_registry
from efficiency_platform_agent.orchestration.runtime import GraphRuntime
from efficiency_platform_agent.persistence.in_memory import (
    FixedClock,
    InMemoryRunEventStore,
    InMemoryRunRepository,
    SequenceIdGenerator,
)
from efficiency_platform_agent.routing.strategy_router import StrategyRouter

from .service import AgentRuntimeService


class _ScriptedModelRuntime:
    """按脚本返回结构化 ProviderResult，不读取网络或环境。"""

    def __init__(self, scripts: Sequence[ProviderResult] | None = None) -> None:
        self.scripts = tuple(scripts or ())
        self.calls = 0

    async def complete(self, *_args: Any, **_kwargs: Any) -> ProviderResult:
        self.calls += 1
        if self.calls <= len(self.scripts):
            return self.scripts[self.calls - 1]
        return ProviderResult(
            "s2/1",
            ProviderMessage("assistant", JsonObject((("content", "fake-response"),))),
            ProviderUsage(1, 1, 0, 0, 1),
        )


class _StateContextBuilder:
    """接受 Graph State 的最小上下文 Fake。"""

    def __init__(self) -> None:
        self._builder = ContextBuilder()

    async def build(self, state: dict[str, Any]) -> Any:
        del state
        return type("Built", (), {"estimated_input_tokens": 0})()


class _SyntheticToolRuntime:
    """Workflow 使用的固定合成 Tool。"""

    def __init__(self) -> None:
        self.calls = 0

    async def invoke(self, *_args: Any, **_kwargs: Any) -> JsonObject:
        self.calls += 1
        return JsonObject((("lookup", "synthetic-result"),))


def build_s2_test_service(
    provider_scripts: Sequence[ProviderResult] | None = None,
    *,
    clock: Any | None = None,
    id_generator: Any | None = None,
) -> AgentRuntimeService:
    """构造仅供 S2 测试的 Direct/Workflow Harness。"""

    resolved_clock = clock or FixedClock(1_000)
    resolved_ids = id_generator or SequenceIdGenerator()
    repository = InMemoryRunRepository()
    event_store = InMemoryRunEventStore()
    cancellation = InMemoryCancellationSignal()
    model_runtime = _ScriptedModelRuntime(provider_scripts)
    context_builder = _StateContextBuilder()
    tool_runtime = _SyntheticToolRuntime()
    checkpointer = None
    registry = build_default_registry(
        model_runtime=model_runtime,
        context_builder=context_builder,
        tool_runtime=tool_runtime,
        checkpointer=checkpointer,
        allow_waiting_input=True,
    )
    router = StrategyRouter(
        registry.available_modes(),
        registered_workflow_ids=frozenset({"synthetic_review/1"}),
    )
    graph_runtime = GraphRuntime(
        registry, cancellation_signal=cancellation, clock=resolved_clock
    )
    budget = ExecutionBudget(
        max_iterations=20,
        max_tool_calls=10,
        max_input_tokens=20_000,
        max_output_tokens=20_000,
        timeout_ms=60_000,
        max_cost_microunits=1_000_000,
    )
    service = AgentRuntimeService(
        repository=repository,
        event_store=event_store,
        router=router,
        graph_runtime=graph_runtime,
        budget_guard=BudgetGuard(),
        budget=budget,
        clock=resolved_clock,
        id_generator=resolved_ids,
        cancellation_signal=cancellation,
    )
    object.__setattr__(
        service, "provider_call_count", lambda _run_id: model_runtime.calls
    )
    object.__setattr__(service, "tool_call_count", lambda _run_id: tool_runtime.calls)
    return service


__all__ = ["build_s2_test_service"]
