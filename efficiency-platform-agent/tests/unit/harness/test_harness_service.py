"""Harness 生命周期、幂等与事件顺序的最小 RED 契约。"""

from __future__ import annotations

import inspect

import pytest

from efficiency_platform_agent.contracts.requests import (
    CreateRunRequestV1,
    ResumeRunRequestV1,
)
from efficiency_platform_agent.core.budget import BudgetGuard
from efficiency_platform_agent.core.diagnostics import (
    DiagnosticRecord,
    RunDiagnosticContext,
    current_diagnostic_context,
)
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.orchestration.contracts import (
    CheckpointView,
    GraphExecutionResult,
)
from efficiency_platform_agent.routing.strategy_router import StrategyRouter


class _RecordingRepository:
    """记录 Run 持久化顺序并委托给内存仓储。"""

    def __init__(self, operations: list[str] | None = None) -> None:
        from efficiency_platform_agent.persistence.in_memory import (
            InMemoryRunRepository,
        )

        self.delegate = InMemoryRunRepository()
        self.operations = operations if operations is not None else []

    async def create(self, record) -> None:
        self.operations.append("run_create")
        await self.delegate.create(record)

    async def get(self, run_id, tenant_id):
        return await self.delegate.get(run_id, tenant_id)

    async def get_by_request_id(self, request_id, tenant_id):
        return await self.delegate.get_by_request_id(request_id, tenant_id)

    async def save(self, record, expected_version) -> None:
        self.operations.append("run_save")
        await self.delegate.save(record, expected_version)


class _RecordingEventStore:
    """记录事件追加顺序并委托给内存事件存储。"""

    def __init__(self, operations: list[str] | None = None) -> None:
        from efficiency_platform_agent.persistence.in_memory import (
            InMemoryRunEventStore,
        )

        self.delegate = InMemoryRunEventStore()
        self.operations = operations if operations is not None else []

    async def append(self, event) -> None:
        self.operations.append(f"event:{event.event_type}")
        await self.delegate.append(event)

    async def list_after(self, run_id, tenant_id, after_sequence):
        return await self.delegate.list_after(run_id, tenant_id, after_sequence)


class _Graph:
    """可控图 Fake，用于证明 Harness 不绕过 Runtime。"""

    def __init__(self, status: RunStatus = RunStatus.SUCCEEDED) -> None:
        self.status = status
        self.calls = 0
        self.resume_calls = 0

    async def execute(self, selection, initial_state):
        self.calls += 1
        raw_budget = initial_state["budget_state"]
        budget_state = BudgetGuard().start(
            ExecutionBudget(10, 2, 100, 100, 100, 100),
            now_epoch_ms=raw_budget["started_at_epoch_ms"],
        )
        return GraphExecutionResult(
            usage=UsageSnapshot(1, 2, 3, estimated=True),
            budget_state=budget_state,
            checkpoint=CheckpointView(
                initial_state["run_id"], f"s2:{selection.mode}:1", "cp-1"
            ),
            facts=(),
            next_status=self.status,
            output=JsonObject((("content", "ok"),))
            if self.status is RunStatus.SUCCEEDED
            else None,
        )

    def validate_resume(self, selection, checkpoint, resume_value):
        return None

    async def resume(
        self, selection, run_id, checkpoint_id, resume_value, *, tenant_id=""
    ):
        self.resume_calls += 1
        return GraphExecutionResult(
            usage=UsageSnapshot(),
            budget_state=BudgetGuard().start(
                ExecutionBudget(3, 1, 100, 100, 100, 100), now_epoch_ms=1
            ),
            checkpoint=CheckpointView(run_id, f"s2:{selection.mode}:1", checkpoint_id),
            facts=(),
            output=JsonObject((("content", "resumed"),)),
        )

    async def get_checkpoint(self, selection, run_id, *, tenant_id=""):
        return CheckpointView(run_id, f"s2:{selection.mode}:1", "cp-1")


class _ExplodingResumeGraph(_Graph):
    """首次进入等待态，并在恢复阶段抛出稳定异常。"""

    class _StableError(RuntimeError):
        """携带可归一化错误码的合成异常。"""

        code = "SYNTHETIC_STABLE"

    def __init__(self) -> None:
        super().__init__(RunStatus.WAITING_INPUT)
        self.resume_context = RunDiagnosticContext()

    async def resume(
        self, selection, run_id, checkpoint_id, resume_value, *, tenant_id=""
    ):
        """保存当前上下文后模拟恢复失败。"""

        del selection, run_id, checkpoint_id, resume_value, tenant_id
        self.resume_context = current_diagnostic_context()
        raise self._StableError("不得进入诊断日志的恢复异常正文")


class _DiagnosticRecorder:
    """保存记录发生时的 Run 关联上下文。"""

    def __init__(self) -> None:
        self.items: list[tuple[DiagnosticRecord, RunDiagnosticContext]] = []

    def record(self, record: DiagnosticRecord) -> None:
        self.items.append((record, current_diagnostic_context()))


def _request(
    request_id: str = "req-1", tenant_id: str = "tenant-1"
) -> CreateRunRequestV1:
    return CreateRunRequestV1(
        request_id=request_id,
        tenant_id=tenant_id,
        user_id="user-1",
        input_text="hello",
        requested_strategy=StrategyMode.DIRECT,
    )


@pytest.mark.asyncio
async def test_harness_persists_lifecycle_in_checkpoint_run_event_order() -> None:
    from efficiency_platform_agent.harness.service import AgentRuntimeService
    from efficiency_platform_agent.persistence.in_memory import (
        FixedClock,
        InMemoryRunEventStore,
        InMemoryRunRepository,
        SequenceIdGenerator,
    )

    graph = _Graph()
    budget = ExecutionBudget(10, 2, 100, 100, 100, 100)
    service = AgentRuntimeService(
        repository=InMemoryRunRepository(),
        event_store=InMemoryRunEventStore(),
        router=StrategyRouter(frozenset({StrategyMode.DIRECT})),
        graph_runtime=graph,
        budget_guard=BudgetGuard(),
        budget=budget,
        clock=FixedClock(1),
        id_generator=SequenceIdGenerator(),
    )
    received_event_types: list[str] = []

    async def record_event(event) -> None:
        """按回调发生顺序记录已经持久化的事件。"""
        received_event_types.append(event.event_type)

    service.add_run_event_listener(record_event)

    result = await service.create_and_execute(_request())

    assert result.status is RunStatus.SUCCEEDED
    assert graph.calls == 1
    events = await service.list_events(result.run_id, "tenant-1")
    assert [event.event_type for event in events] == [
        "run_created",
        "run_queued",
        "strategy_selected",
        "run_started",
        "checkpoint_saved",
        "run_succeeded",
    ]
    assert received_event_types == [event.event_type for event in events]
    assert events[-2].sequence < events[-1].sequence


@pytest.mark.asyncio
async def test_harness_ignores_run_event_listener_failure() -> None:
    """事件监听器失败不得截断 Run 生命周期或改变成功结果。"""

    from efficiency_platform_agent.harness.service import AgentRuntimeService
    from efficiency_platform_agent.persistence.in_memory import (
        FixedClock,
        InMemoryRunEventStore,
        InMemoryRunRepository,
        SequenceIdGenerator,
    )

    service = AgentRuntimeService(
        repository=InMemoryRunRepository(),
        event_store=InMemoryRunEventStore(),
        router=StrategyRouter(frozenset({StrategyMode.DIRECT})),
        graph_runtime=_Graph(),
        budget_guard=BudgetGuard(),
        budget=ExecutionBudget(10, 2, 100, 100, 100, 100),
        clock=FixedClock(1),
        id_generator=SequenceIdGenerator(),
    )

    async def fail_after_persistence(event) -> None:
        """模拟终端日志写入异常。"""
        del event
        raise RuntimeError("合成监听器失败")

    service.add_run_event_listener(fail_after_persistence)

    result = await service.create_and_execute(_request("req-listener-failure"))

    assert result.status is RunStatus.SUCCEEDED
    events = await service.list_events(result.run_id, "tenant-1")
    assert events[-1].event_type == "run_succeeded"


@pytest.mark.asyncio
async def test_harness_ignores_run_state_listener_failure() -> None:
    """状态监听器失败不得覆盖已经形成的 Run 成功终态。"""

    from efficiency_platform_agent.harness.service import AgentRuntimeService
    from efficiency_platform_agent.persistence.in_memory import (
        FixedClock,
        InMemoryRunEventStore,
        InMemoryRunRepository,
        SequenceIdGenerator,
    )

    service = AgentRuntimeService(
        repository=InMemoryRunRepository(),
        event_store=InMemoryRunEventStore(),
        router=StrategyRouter(frozenset({StrategyMode.DIRECT})),
        graph_runtime=_Graph(),
        budget_guard=BudgetGuard(),
        budget=ExecutionBudget(10, 2, 100, 100, 100, 100),
        clock=FixedClock(1),
        id_generator=SequenceIdGenerator(),
    )

    async def fail_after_terminal_state(view) -> None:
        """模拟终态日志写入异常。"""
        del view
        raise RuntimeError("合成状态监听器失败")

    service.add_run_state_listener(fail_after_terminal_state)

    result = await service.create_and_execute(_request("req-state-listener-failure"))

    assert result.status is RunStatus.SUCCEEDED
    stored = await service.get_run(result.run_id, "tenant-1")
    assert stored.status is RunStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_harness_records_pipeline_failure_with_run_context_without_exception_text() -> (
    None
):
    """后台 Pipeline 异常须保持安全终态并带回 Run 关联字段。"""

    from efficiency_platform_agent.harness.service import AgentRuntimeService
    from efficiency_platform_agent.persistence.in_memory import (
        FixedClock,
        InMemoryRunEventStore,
        InMemoryRunRepository,
        SequenceIdGenerator,
    )

    recorder = _DiagnosticRecorder()
    service = AgentRuntimeService(
        repository=InMemoryRunRepository(),
        event_store=InMemoryRunEventStore(),
        router=StrategyRouter(frozenset({StrategyMode.DIRECT})),
        graph_runtime=_Graph(),
        budget_guard=BudgetGuard(),
        budget=ExecutionBudget(10, 2, 100, 100, 100, 100),
        clock=FixedClock(1),
        id_generator=SequenceIdGenerator(),
        diagnostic_recorder=recorder,
    )

    async def explode(_context):
        raise ValueError("pipeline secret must not be recorded")

    queued = await service.create_and_schedule_pipeline(
        _request("req-pipeline-diagnostic"), explode
    )
    await service.wait_for_background_tasks()
    completed = await service.get_run(queued.run_id, "tenant-1")

    assert completed.status is RunStatus.FAILED
    record, context = recorder.items[-1]
    assert record.event_name == "pipeline_preparation_failed"
    assert record.error_code == "PIPELINE_PREPARATION_FAILED"
    assert record.error_type == "ValueError"
    assert record.error_location is not None
    assert context.run_id == queued.run_id
    assert context.request_id == "req-pipeline-diagnostic"
    assert "pipeline secret must not be recorded" not in repr(recorder.items)
    assert current_diagnostic_context() == RunDiagnosticContext()


@pytest.mark.asyncio
async def test_resume_failure_records_safe_error_with_original_run_context() -> None:
    """恢复调用和失败诊断须关联原 Run、请求与策略。"""

    from efficiency_platform_agent.harness.service import AgentRuntimeService
    from efficiency_platform_agent.persistence.in_memory import (
        FixedClock,
        InMemoryRunEventStore,
        InMemoryRunRepository,
        SequenceIdGenerator,
    )

    graph = _ExplodingResumeGraph()
    recorder = _DiagnosticRecorder()
    service = AgentRuntimeService(
        repository=InMemoryRunRepository(),
        event_store=InMemoryRunEventStore(),
        router=StrategyRouter(frozenset({StrategyMode.DIRECT})),
        graph_runtime=graph,
        budget_guard=BudgetGuard(),
        budget=ExecutionBudget(10, 2, 100, 100, 100, 100),
        clock=FixedClock(1),
        id_generator=SequenceIdGenerator(),
        diagnostic_recorder=recorder,
    )
    waiting = await service.create_and_execute(_request("req-resume-diagnostic"))
    recorder.items.clear()

    result = await service.resume_run(
        waiting.run_id,
        ResumeRunRequestV1(
            tenant_id="tenant-1",
            checkpoint_id=waiting.checkpoint_id or "cp-1",
            resume_value={},
        ),
    )

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "SYNTHETIC_STABLE"
    assert graph.resume_context.run_id == waiting.run_id
    assert graph.resume_context.request_id == "req-resume-diagnostic"
    assert graph.resume_context.strategy == "direct"
    record, context = recorder.items[-1]
    assert record.event_name == "graph_resume_failed"
    assert record.stage == "graph.resume"
    assert record.error_code == "SYNTHETIC_STABLE"
    assert context == graph.resume_context
    assert "不得进入诊断日志的恢复异常正文" not in repr(recorder.items)
    assert current_diagnostic_context() == RunDiagnosticContext()


@pytest.mark.asyncio
async def test_background_failure_records_actual_code_stage_and_persisted_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """后台边界失败不得伪装成准备阶段错误或丢失已持久化策略。"""

    from efficiency_platform_agent.harness.service import AgentRuntimeService
    from efficiency_platform_agent.persistence.in_memory import (
        FixedClock,
        InMemoryRunEventStore,
        InMemoryRunRepository,
        SequenceIdGenerator,
    )

    class _StableError(RuntimeError):
        code = "SYNTHETIC_STABLE"

    recorder = _DiagnosticRecorder()
    service = AgentRuntimeService(
        repository=InMemoryRunRepository(),
        event_store=InMemoryRunEventStore(),
        router=StrategyRouter(frozenset({StrategyMode.DIRECT})),
        graph_runtime=_Graph(),
        budget_guard=BudgetGuard(),
        budget=ExecutionBudget(10, 2, 100, 100, 100, 100),
        clock=FixedClock(1),
        id_generator=SequenceIdGenerator(),
        diagnostic_recorder=recorder,
    )

    async def explode(record, request):
        """模拟策略已持久化后在后台最外层冒出的异常。"""

        del request
        await service._transition(record, RunStatus.RUNNING, strategy=StrategyMode.DIRECT)
        raise _StableError("不得进入诊断日志的后台异常正文")

    monkeypatch.setattr(service, "_execute_queued", explode)
    queued = await service.create_and_schedule(_request("req-background-diagnostic"))
    await service.wait_for_background_tasks()

    record, context = recorder.items[-1]
    assert record.event_name == "background_execution_failed"
    assert record.stage == "background.execute"
    assert record.error_code == "SYNTHETIC_STABLE"
    assert context.run_id == queued.run_id
    assert context.request_id == "req-background-diagnostic"
    assert context.strategy == "direct"
    assert "不得进入诊断日志的后台异常正文" not in repr(recorder.items)


@pytest.mark.asyncio
async def test_harness_saves_run_before_publishing_checkpoint_event() -> None:
    """Checkpoint 事件必须在 Run CAS 成功后才对外追加。"""

    from efficiency_platform_agent.harness.service import AgentRuntimeService
    from efficiency_platform_agent.persistence.in_memory import (
        FixedClock,
        SequenceIdGenerator,
    )

    operations: list[str] = []
    repository = _RecordingRepository(operations)
    event_store = _RecordingEventStore(operations)
    service = AgentRuntimeService(
        repository=repository,
        event_store=event_store,
        router=StrategyRouter(frozenset({StrategyMode.DIRECT})),
        graph_runtime=_Graph(),
        budget_guard=BudgetGuard(),
        budget=ExecutionBudget(10, 2, 100, 100, 100, 100),
        clock=FixedClock(1),
        id_generator=SequenceIdGenerator(),
    )

    result = await service.create_and_execute(_request("req-order"))

    assert result.status is RunStatus.SUCCEEDED
    checkpoint_event_index = operations.index("event:checkpoint_saved")
    run_save_indices = [
        index for index, operation in enumerate(operations) if operation == "run_save"
    ]
    assert run_save_indices
    assert run_save_indices[-1] < checkpoint_event_index


@pytest.mark.asyncio
async def test_harness_idempotency_is_tenant_scoped_and_does_not_execute_twice() -> (
    None
):
    from efficiency_platform_agent.harness.service import AgentRuntimeService
    from efficiency_platform_agent.persistence.in_memory import (
        FixedClock,
        InMemoryRunEventStore,
        InMemoryRunRepository,
        SequenceIdGenerator,
    )

    graph = _Graph()
    service = AgentRuntimeService(
        repository=InMemoryRunRepository(),
        event_store=InMemoryRunEventStore(),
        router=StrategyRouter(frozenset({StrategyMode.DIRECT})),
        graph_runtime=graph,
        budget_guard=BudgetGuard(),
        budget=ExecutionBudget(10, 2, 100, 100, 100, 100),
        clock=FixedClock(1),
        id_generator=SequenceIdGenerator(),
    )
    first = await service.create_and_execute(_request())
    again = await service.create_and_execute(_request())
    other = await service.create_and_execute(_request(tenant_id="tenant-2"))

    assert again.run_id == first.run_id
    assert other.run_id != first.run_id
    assert graph.calls == 2


def test_harness_public_service_has_only_governed_lifecycle_methods() -> None:
    from efficiency_platform_agent.harness.service import AgentRuntimeService

    assert str(inspect.signature(AgentRuntimeService.create_and_execute)).startswith(
        "(self, request"
    )
    assert not hasattr(AgentRuntimeService, "execute_strategy")
