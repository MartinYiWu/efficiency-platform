"""正式后台Pipeline创建原Run控制器，Graph和刷新等待复用，退出释放正文。"""

import asyncio
import time
from dataclasses import replace

from efficiency_platform_agent.contracts.requests import CancelRunRequestV1
from efficiency_platform_agent.core.budget import BudgetCharge, BudgetGuard, BudgetState
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.execution_control import current_run_control
from efficiency_platform_agent.core.memory_execution import MemoryExecutionRecord
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject
from efficiency_platform_agent.core.run_context_binding import bind_conversation_scope
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.harness.service import (
    AgentRuntimeService,
    RunPipelinePreparation,
)
from efficiency_platform_agent.orchestration.contracts import (
    CheckpointView,
    GraphExecutionResult,
)
from efficiency_platform_agent.persistence.in_memory import (
    FixedClock,
    InMemoryRunEventStore,
    InMemoryRunRepository,
    SequenceIdGenerator,
)
from efficiency_platform_agent.routing.strategy_router import StrategyRouter
from tests.integration.context_control.test_memory_execution_mysql import context
from tests.unit.harness.test_memory_run_binding import request


def runtime_case(*, refresh_enabled=True):
    now = int(time.time())
    memory = context()
    packet = replace(memory.packet, issued_at=now, expires_at=now + 30)
    from efficiency_platform_agent.security.memory_packet import (
        memory_packet_digest,
        memory_packet_semantic_digest,
    )

    memory = replace(
        memory,
        packet=packet,
        deadline_epoch_seconds=now + 45,
        packet_digest=memory_packet_digest(packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(packet),
    )

    class Store:
        async def get(self, *args):
            return None

        async def claim(self, ctx, run_id, kind, fingerprint, budget_deadline):
            return MemoryExecutionRecord(
                ctx,
                run_id,
                kind,
                fingerprint,
                min(ctx.deadline_epoch_seconds, budget_deadline),
                "ACTIVE",
                packet.execution_revision,
                packet.grant_epoch,
                packet.source_epoch,
                packet.deletion_epoch,
            ), True

    runtime = AgentRuntimeService(
        repository=InMemoryRunRepository(),
        event_store=InMemoryRunEventStore(),
        router=StrategyRouter(frozenset({StrategyMode.DIRECT})),
        graph_runtime=None,
        budget_guard=BudgetGuard(),
        budget=ExecutionBudget(10, 0, 20000, 2000, 60000, 100000),
        clock=FixedClock(now * 1000),
        id_generator=SequenceIdGenerator(),
        memory_execution_store=Store(),
        memory_refresh_enabled=refresh_enabled,
    )
    return (
        runtime,
        memory,
        request(
            request_id="original-pipeline",
            tenant_id=packet.scope.tenant_id,
            user_id=packet.scope.user_id,
        ),
    )


async def test_formal_schedule_pipeline_uses_one_original_control_through_graph_and_clears_body():
    runtime, memory, original = runtime_case()
    seen = []
    graph_seen = []

    class Graph:
        async def execute(self, selection, state):
            control = current_run_control()
            assert control is not None and control is seen[0]
            graph_seen.append(control)
            control.results["private-synthetic"] = object()
            return GraphExecutionResult(
                usage=UsageSnapshot(),
                budget_state=BudgetState(
                    BudgetCharge(),
                    state["budget_state"]["started_at_epoch_ms"],
                    state["budget_state"]["deadline_epoch_ms"],
                ),
                checkpoint=CheckpointView(state["run_id"], "s2:direct:1", "cp"),
                facts=(),
                next_status=RunStatus.SUCCEEDED,
                output=JsonObject((("content", "synthetic"),)),
            )

    runtime.graph_runtime = Graph()

    async def prepare(context_value):
        control = current_run_control()
        assert control is not None
        seen.append(control)
        assert control.deadline <= time.monotonic() + 45.1
        return RunPipelinePreparation(original)

    with bind_conversation_scope(memory.packet.scope, memory_context=memory):
        queued = await runtime.create_and_schedule_pipeline(original, prepare)
    await runtime.wait_for_background_tasks()
    result = await runtime.get_run(queued.run_id, original.tenant_id)
    # 本例Graph仅观察控制器，不提供RESULT能力，正文必须被生产门禁拒绝。
    assert result.status == RunStatus.FAILED and graph_seen == seen
    assert len(seen) == 1 and seen[0].calls == 0
    assert (
        seen[0].stopped is not None
        and not seen[0].results
        and not seen[0].pending
        and not seen[0].streams
    )
    assert not runtime._memory_run_controls
    assert current_run_control() is None


async def test_cancel_stops_original_pipeline_control_and_closes_stream_before_owner_exit():
    runtime, memory, original = runtime_case()
    entered = asyncio.Event()
    facts = []

    async def prepare(context_value):
        control = current_run_control()
        assert control is not None

        async def close():
            facts.append("stream-closed")

        control.streams["synthetic"] = close
        facts.append(control)
        entered.set()
        while True:
            control.check()
            await asyncio.sleep(0.01)

    with bind_conversation_scope(memory.packet.scope, memory_context=memory):
        queued = await runtime.create_and_schedule_pipeline(original, prepare)
    await asyncio.wait_for(entered.wait(), 1)
    await runtime.cancel_run(
        queued.run_id, CancelRunRequestV1(tenant_id=original.tenant_id)
    )
    assert facts[0].stopped is not None
    await asyncio.wait_for(runtime.wait_for_background_tasks(), 1)
    await runtime.stop_memory_execution(queued.run_id, original.tenant_id)
    assert facts[-1] == "stream-closed" and not runtime._memory_run_controls


async def test_two_original_runs_have_isolated_controls_and_cancel_only_its_owner():
    runtime, memory, first = runtime_case()
    from efficiency_platform_agent.security.memory_packet import (
        memory_packet_digest,
        memory_packet_semantic_digest,
    )

    packet = replace(
        memory.packet, execution_id="second-execution", task_id="second-task"
    )
    second_memory = replace(
        memory,
        packet=packet,
        packet_digest=memory_packet_digest(packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(packet),
    )
    second = first.model_copy(update={"request_id": "second-request"})
    controls = {}
    entered = asyncio.Event()
    release_second = asyncio.Event()

    async def prepare(ctx):
        control = current_run_control()
        assert control is not None
        controls[ctx.run_id] = control
        if len(controls) == 2:
            entered.set()
        while True:
            control.check()
            if release_second.is_set():
                raise ValueError("synthetic finish")
            await asyncio.sleep(0.01)

    with bind_conversation_scope(memory.packet.scope, memory_context=memory):
        one = await runtime.create_and_schedule_pipeline(first, prepare)
    with bind_conversation_scope(
        second_memory.packet.scope, memory_context=second_memory
    ):
        two = await runtime.create_and_schedule_pipeline(second, prepare)
    await asyncio.wait_for(entered.wait(), 1)
    try:
        assert controls[one.run_id] is not controls[two.run_id]
        await runtime.stop_memory_execution(one.run_id, first.tenant_id)
        assert (
            controls[one.run_id].stopped is not None
            and controls[two.run_id].stopped is None
        )
        assert (second.tenant_id, two.run_id) in runtime._memory_run_controls
    finally:
        release_second.set()
        await runtime.wait_for_background_tasks()
    assert not runtime._memory_run_controls


async def test_unknown_callers_control_is_rejected_without_stop_or_replacement():
    from efficiency_platform_agent.core.execution_control import (
        RunControl,
        execution_scope,
    )

    runtime, memory, original = runtime_case()
    foreign = RunControl()
    foreign.results["unrelated-private-marker"] = object()
    called = []

    async def prepare(ctx):
        called.append(ctx)
        return RunPipelinePreparation(original)

    with (
        execution_scope(foreign),
        bind_conversation_scope(memory.packet.scope, memory_context=memory),
    ):
        queued = await runtime.create_and_schedule_pipeline(original, prepare)
        await runtime.wait_for_background_tasks()
        assert current_run_control() is foreign
    assert not called and foreign.stopped is None and len(foreign.results) == 1
    assert not runtime._memory_run_controls
    assert (
        await runtime.get_run(queued.run_id, original.tenant_id)
    ).status == RunStatus.FAILED


async def test_refresh_flag_off_keeps_original_background_control_behavior():
    runtime, memory, original = runtime_case(refresh_enabled=False)
    seen = []

    async def prepare(ctx):
        seen.append(current_run_control())
        raise ValueError("synthetic finish")

    with bind_conversation_scope(memory.packet.scope, memory_context=memory):
        await runtime.create_and_schedule_pipeline(original, prepare)
    await runtime.wait_for_background_tasks()
    assert seen == [None] and not runtime._memory_run_controls
