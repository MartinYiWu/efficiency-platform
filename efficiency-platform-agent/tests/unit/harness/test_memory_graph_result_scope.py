"""记忆结果沿原Harness保存/取消语义，且只在认证结果scope内执行一次。"""

from dataclasses import replace

import pytest

from efficiency_platform_agent.agents.conversation.general_agent import (
    GeneralConversationAgent,
)
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.orchestration.builders.conversation_direct import (
    build_conversation_direct_registration,
)
from efficiency_platform_agent.orchestration.registry import GraphRegistry
from efficiency_platform_agent.routing.strategy_router import StrategyRouter
from tests.orchestration.test_conversation_direct_runtime import FakeModelRuntime
from tests.unit.harness.test_harness_service import _Graph
from tests.unit.harness.test_memory_run_binding import request, service


@pytest.mark.parametrize("cancel", [False, True])
async def test_harness_uses_memory_result_callback_once_with_original_budget(cancel):
    runtime = service()
    runtime.router = StrategyRouter(frozenset({StrategyMode.DIRECT}))
    graphs = GraphRegistry()

    async def resolver(*args):
        pytest.fail("本例不执行Graph节点")

    graphs.register(
        build_conversation_direct_registration(
            GeneralConversationAgent(FakeModelRuntime()), resolver, memory_gate=object()
        )
    )

    class Graph(_Graph):
        registry = graphs
        inside = False
        callbacks = 0

        async def execute(self, *args):
            pytest.fail("记忆结果不得经过普通execute后在scope外保存")

        async def execute_memory_context(self, selection, state, callback):
            result = await super().execute(selection, state)
            result = replace(
                result,
                budget_state=replace(
                    result.budget_state,
                    deadline_epoch_ms=result.budget_state.deadline_epoch_ms + 1000,
                ),
            )
            if cancel:
                runtime._cancelled_runs.add(state["run_id"])
            self.inside = True
            try:
                self.callbacks += 1
                return await callback(result)
            finally:
                self.inside = False

    graph = Graph()
    runtime.graph_runtime = graph
    applied = []
    original = runtime._apply_graph_result

    async def apply(record, result):
        assert graph.inside
        assert (
            result.budget_state.deadline_epoch_ms
            == record.budget_state.deadline_epoch_ms
        )
        assert (
            result.budget_state.started_at_epoch_ms
            == record.budget_state.started_at_epoch_ms
        )
        applied.append(result.next_status)
        return await original(record, result)

    runtime._apply_graph_result = apply
    view = await runtime.create_and_execute(request())
    expected = RunStatus.CANCELLED if cancel else RunStatus.SUCCEEDED
    assert view.status == expected.value
    assert applied == [expected] and graph.callbacks == 1 and not graph.inside


@pytest.mark.parametrize(
    "status",
    [RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.TIMED_OUT, RunStatus.SUCCEEDED],
)
async def test_memory_graph_failure_returns_governed_run_view_without_unguarded_success(
    status,
):
    from efficiency_platform_agent.core.runtime import RunFailure

    runtime = service()
    runtime.router = StrategyRouter(frozenset({StrategyMode.DIRECT}))
    graphs = GraphRegistry()

    async def resolver(*args):
        pytest.fail("不应进入Provider")

    graphs.register(
        build_conversation_direct_registration(
            GeneralConversationAgent(FakeModelRuntime()), resolver, memory_gate=object()
        )
    )

    class Graph(_Graph):
        registry = graphs

        async def execute_memory_context(self, selection, state, callback):
            self.calls += 1
            result = await super().execute(selection, state)
            return replace(
                result,
                next_status=status,
                output=result.output if status == RunStatus.SUCCEEDED else None,
                failure=RunFailure(
                    "MEMORY_ACCESS_REVOKED", "authority", False, "权限已失效"
                )
                if status in {RunStatus.FAILED, RunStatus.TIMED_OUT}
                else None,
            )

    graph = Graph()
    runtime.graph_runtime = graph
    view = await runtime.create_and_execute(request())
    expected = RunStatus.FAILED if status == RunStatus.SUCCEEDED else status
    assert hasattr(view, "status") and view.status == expected.value
    saved = await runtime.repository.get(view.run_id, "t")
    assert saved.status == expected and saved.output is None
    events = await runtime.event_store.list_after(view.run_id, "t", 0)
    assert (
        sum(
            event.event_type
            == {
                RunStatus.FAILED: "run_failed",
                RunStatus.CANCELLED: "run_cancelled",
                RunStatus.TIMED_OUT: "run_timed_out",
            }[expected]
            for event in events
        )
        == 1
    )
    assert not any(event.event_type == "run_succeeded" for event in events)
