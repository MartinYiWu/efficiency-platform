import inspect
from types import SimpleNamespace

import pytest

from efficiency_platform_agent.core.diagnostics import (
    DiagnosticRecord,
    RunDiagnosticContext,
    bind_diagnostic_context,
    current_diagnostic_context,
)
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import JsonObject
from efficiency_platform_agent.orchestration.checkpoint import CheckpointRecord
from efficiency_platform_agent.orchestration.contracts import (
    GraphRegistration,
)
from efficiency_platform_agent.orchestration.registry import GraphRegistry
from efficiency_platform_agent.orchestration.runtime import GraphRuntime


class _StaticProgram:
    """返回固定状态的图程序替身。"""

    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    async def invoke(self, _initial_state, _config):
        return self.values

    async def resume(self, _resume_value, _config):
        return self.values

    async def get_state(self, _config):
        return self.values


class _StaticBuilder:
    """构造固定图程序的构建器替身。"""

    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def build(self):
        return _StaticProgram(self.values)


class _PayloadAdapter:
    """接受空策略载荷的测试适配器。"""

    def adapt(self, _schema_version, payload):
        return SimpleNamespace(schema_version="strategy.none/1", data=payload)


class _DiagnosticRecorder:
    """收集图异常的白名单诊断事实及当时上下文。"""

    def __init__(self) -> None:
        self.items: list[tuple[DiagnosticRecord, RunDiagnosticContext]] = []

    def record(self, record: DiagnosticRecord) -> None:
        self.items.append((record, current_diagnostic_context()))


class _AsyncCheckpointStore:
    """模拟 PostgreSQL 等异步 Checkpoint 存储端口。"""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], CheckpointRecord] = {}

    async def save(
        self,
        run_id: str,
        checkpoint_ns: str,
        state: dict[str, object],
        *,
        tenant_id: str = "",
        resume_binding=None,
        checkpoint_id: str | None = None,
    ):
        from efficiency_platform_agent.orchestration.checkpoint import (
            InMemoryCheckpointStore,
        )

        view = InMemoryCheckpointStore().save(
            run_id,
            checkpoint_ns,
            state,
            tenant_id=tenant_id,
            resume_binding=resume_binding,
            checkpoint_id=checkpoint_id,
        )
        record = CheckpointRecord(view, dict(state))
        self._records[(tenant_id, run_id, checkpoint_ns)] = record
        return view

    async def get(self, run_id: str, checkpoint_ns: str, tenant_id: str = ""):
        return self._records.get((tenant_id, run_id, checkpoint_ns))


def test_runtime_has_one_exact_execute_signature() -> None:
    assert list(inspect.signature(GraphRuntime.execute).parameters) == [
        "self",
        "selection",
        "initial_state",
    ]
    assert "StrategyMode" not in inspect.getsource(GraphRuntime.execute)


def test_registry_rejects_duplicate_and_unknown_modes() -> None:
    registry = GraphRegistry()
    registration = GraphRegistration(
        graph_id="direct",
        strategy=StrategyMode.DIRECT,
        graph_version="1.0.0",
        checkpoint_ns="s2:direct:1",
        strategy_payload_schema_version="strategy.none/1",
        allowed_strategy_payload_keys=frozenset(),
        allowed_next_statuses=frozenset({RunStatus.SUCCEEDED}),
        builder=object(),
        payload_adapter=object(),
    )
    registry.register(registration)
    with pytest.raises(ValueError):
        registry.register(registration)
    with pytest.raises(KeyError):
        registry.get(StrategyMode.WORKFLOW)


@pytest.mark.parametrize("status", [RunStatus.FAILED, RunStatus.TIMED_OUT])
@pytest.mark.asyncio
async def test_runtime_rejects_terminal_status_with_success_output(
    status: RunStatus,
) -> None:
    """终态失败类状态携带成功输出时必须失败关闭并清除输出。"""

    registry = GraphRegistry()
    registry.register(
        GraphRegistration(
            graph_id="invalid-terminal",
            strategy=StrategyMode.DIRECT,
            graph_version="1.0.0",
            checkpoint_ns="s2:direct:1",
            strategy_payload_schema_version="strategy.none/1",
            allowed_strategy_payload_keys=frozenset(),
            allowed_next_statuses=frozenset(
                {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.TIMED_OUT}
            ),
            builder=_StaticBuilder(
                {"next_status": status.value, "output": {"content": "不应保留"}}
            ),
            payload_adapter=_PayloadAdapter(),
        )
    )
    runtime = GraphRuntime(registry)

    result = await runtime.execute(
        type("Selection", (), {"mode": StrategyMode.DIRECT})(),
        {
            "run_id": "run-invalid-terminal",
            "strategy_payload": JsonObject(),
        },
    )

    assert result.next_status is RunStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "OUTPUT_SCHEMA_INVALID"
    assert result.output is None


@pytest.mark.asyncio
async def test_runtime_supports_async_checkpoint_store() -> None:
    """GraphRuntime 应兼容异步 Checkpoint 存储而不创建第二运行时。"""

    registry = GraphRegistry()
    registry.register(
        GraphRegistration(
            graph_id="async-checkpoint",
            strategy=StrategyMode.DIRECT,
            graph_version="1.0.0",
            checkpoint_ns="s2:direct:1",
            strategy_payload_schema_version="strategy.none/1",
            allowed_strategy_payload_keys=frozenset(),
            allowed_next_statuses=frozenset({RunStatus.SUCCEEDED}),
            builder=_StaticBuilder(
                {
                    "next_status": RunStatus.SUCCEEDED.value,
                    "output": {"content": "完成"},
                }
            ),
            payload_adapter=_PayloadAdapter(),
        )
    )
    store = _AsyncCheckpointStore()
    runtime = GraphRuntime(registry, checkpoint_store=store)
    selection = type("Selection", (), {"mode": StrategyMode.DIRECT})()

    result = await runtime.execute(
        selection,
        {
            "run_id": "run-async-checkpoint",
            "tenant_id": "tenant-a",
            "strategy_payload": JsonObject(),
        },
    )
    checkpoint = await runtime.get_checkpoint(
        selection, "run-async-checkpoint", tenant_id="tenant-a"
    )

    assert result.next_status is RunStatus.SUCCEEDED
    assert checkpoint is not None
    assert checkpoint.checkpoint_id == result.checkpoint.checkpoint_id
    assert await store.get("run-async-checkpoint", "s2:direct:1", "tenant-b") is None


@pytest.mark.asyncio
async def test_runtime_records_unhandled_graph_exception_without_exception_text() -> None:
    """图执行异常诊断不得改变既有安全失败结果或泄漏正文。"""

    class _ExplodingProgram:
        async def invoke(self, _initial_state, _config):
            raise RuntimeError("graph secret must not be recorded")

    class _ExplodingBuilder:
        def build(self):
            return _ExplodingProgram()

    registry = GraphRegistry()
    registry.register(
        GraphRegistration(
            graph_id="exploding",
            strategy=StrategyMode.DIRECT,
            graph_version="1.0.0",
            checkpoint_ns="s2:direct:1",
            strategy_payload_schema_version="strategy.none/1",
            allowed_strategy_payload_keys=frozenset(),
            allowed_next_statuses=frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED}),
            builder=_ExplodingBuilder(),
            payload_adapter=_PayloadAdapter(),
        )
    )
    recorder = _DiagnosticRecorder()
    runtime = GraphRuntime(registry, diagnostic_recorder=recorder)
    with bind_diagnostic_context(run_id="run-graph", request_id="req-graph"):
        result = await runtime.execute(
            type("Selection", (), {"mode": StrategyMode.DIRECT})(),
            {"run_id": "run-graph", "strategy_payload": JsonObject()},
        )

    assert result.next_status is RunStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "GRAPH_EXECUTION_FAILED"
    record, context = recorder.items[-1]
    assert record.event_name == "graph_execution_failed"
    assert record.error_code == "GRAPH_EXECUTION_FAILED"
    assert record.error_type == "RuntimeError"
    assert record.error_location is not None
    assert context.run_id == "run-graph"
    assert context.request_id == "req-graph"
    assert "graph secret must not be recorded" not in repr(recorder.items)


@pytest.mark.asyncio
async def test_runtime_records_resume_exception_with_resume_stage() -> None:
    """真实恢复异常必须标识恢复阶段，不能伪装成首次执行失败。"""

    class _ExplodingResumeProgram:
        async def invoke(self, _initial_state, _config):
            return {"next_status": RunStatus.WAITING_INPUT.value}

        async def resume(self, _resume_value, _config):
            raise RuntimeError("resume secret must not be recorded")

    class _ExplodingResumeBuilder:
        def build(self):
            return _ExplodingResumeProgram()

    registry = GraphRegistry()
    registry.register(
        GraphRegistration(
            graph_id="exploding-resume",
            strategy=StrategyMode.DIRECT,
            graph_version="1.0.0",
            checkpoint_ns="s2:direct:1",
            strategy_payload_schema_version="strategy.none/1",
            allowed_strategy_payload_keys=frozenset(),
            allowed_next_statuses=frozenset(
                {RunStatus.WAITING_INPUT, RunStatus.FAILED}
            ),
            builder=_ExplodingResumeBuilder(),
            payload_adapter=_PayloadAdapter(),
        )
    )
    recorder = _DiagnosticRecorder()
    runtime = GraphRuntime(registry, diagnostic_recorder=recorder)
    selection = type("Selection", (), {"mode": StrategyMode.DIRECT})()
    first = await runtime.execute(
        selection,
        {"run_id": "run-resume", "strategy_payload": JsonObject()},
    )
    recorder.items.clear()

    with bind_diagnostic_context(
        run_id="run-resume", request_id="req-resume", strategy="direct"
    ):
        result = await runtime.resume(
            selection,
            "run-resume",
            first.checkpoint.checkpoint_id,
            JsonObject(),
        )

    assert result.next_status is RunStatus.FAILED
    record, context = recorder.items[-1]
    assert record.event_name == "graph_resume_failed"
    assert record.stage == "graph.resume"
    assert record.error_code == "GRAPH_EXECUTION_FAILED"
    assert context.run_id == "run-resume"
    assert context.request_id == "req-resume"
    assert context.strategy == "direct"
    assert "resume secret must not be recorded" not in repr(recorder.items)
