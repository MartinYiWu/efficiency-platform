"""统一 Harness 生命周期：请求、Run、Graph、Checkpoint 与事件。"""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, cast

from efficiency_platform_agent.contracts.events import EventType, RunEventV1
from efficiency_platform_agent.contracts.requests import (
    CancelRunRequestV1,
    CreateRunRequestV1,
    ResumeRunRequestV1,
)
from efficiency_platform_agent.contracts.responses import (
    CheckpointViewV1,
    RunErrorV1,
    RunViewV1,
    UsageV1,
)
from efficiency_platform_agent.core.budget import BudgetGuard, BudgetState
from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    JsonValue,
    RunRequest,
)
from efficiency_platform_agent.core.runtime import (
    RunEventRecord,
    RunFailure,
    RunRecord,
    StrategyPayload,
    UsageSnapshot,
)
from efficiency_platform_agent.core.runtime_ports import (
    Clock,
    IdGenerator,
    RunEventStore,
    RunRepository,
)
from efficiency_platform_agent.orchestration.contracts import (
    CheckpointView,
    GraphExecutionResult,
)
from efficiency_platform_agent.orchestration.registry import validate_strategy_payload
from efficiency_platform_agent.routing.strategy_router import (
    StrategyRouter,
)

from .errors import HarnessError, normalize_error


def _json_object(value: Mapping[str, Any]) -> JsonObject:
    """深拷贝并转换为不可变 JsonObject。"""

    def convert(item: Any) -> JsonValue:
        if isinstance(item, Mapping):
            return JsonObject(tuple((str(key), convert(child)) for key, child in copy.deepcopy(dict(item)).items()))
        if isinstance(item, (list, tuple)):
            return tuple(convert(child) for child in copy.deepcopy(list(item)))
        if item is None or isinstance(item, (str, int, float, bool)):
            return item
        raise HarnessError("INVALID_REQUEST", "请求载荷无效", category="request")

    converted = convert(value)
    if not isinstance(converted, JsonObject):
        raise HarnessError("INVALID_REQUEST", "请求载荷无效", category="request")
    return converted


def _plain(value: JsonValue) -> Any:
    """将核心不可变 JSON 值转换为对外响应值。"""

    if isinstance(value, JsonObject):
        return {key: _plain(child) for key, child in value.items}
    if isinstance(value, tuple):
        return [_plain(child) for child in value]
    return value


def _budget_dict(state: BudgetState) -> dict[str, Any]:
    """把预算快照写入 Graph State 的 JSON 字段。"""

    consumed = state.consumed
    return {
        "started_at_epoch_ms": state.started_at_epoch_ms,
        "deadline_epoch_ms": state.deadline_epoch_ms,
        "consumed": {
            "iterations": consumed.iterations,
            "tool_calls": consumed.tool_calls,
            "input_tokens": consumed.input_tokens,
            "output_tokens": consumed.output_tokens,
            "cost_microunits": consumed.cost_microunits,
        },
    }


class AgentRuntimeService:
    """S2 Harness 的唯一公开运行服务。"""

    def __init__(
        self,
        *,
        repository: RunRepository,
        event_store: RunEventStore,
        router: StrategyRouter,
        graph_runtime: Any,
        budget_guard: BudgetGuard,
        budget: ExecutionBudget,
        clock: Clock,
        id_generator: IdGenerator,
        cancellation_signal: Any | None = None,
    ) -> None:
        self.repository = repository
        self.event_store = event_store
        self.router = router
        self.graph_runtime = graph_runtime
        self.budget_guard = budget_guard
        self.budget = budget
        self.clock = clock
        self.id_generator = id_generator
        self.cancellation_signal = cancellation_signal
        self._event_lock = asyncio.Lock()
        self._cancelled_runs: set[str] = set()

    async def create_and_execute(self, request: CreateRunRequestV1) -> RunViewV1:
        """按固定顺序建立 Run、路由、适配 payload 并执行 Graph。"""

        if not isinstance(request, CreateRunRequestV1):
            raise HarnessError("INVALID_REQUEST", "创建请求无效", category="request")
        existing = await self.repository.get_by_request_id(request.request_id, request.tenant_id)
        if existing is not None:
            return self._view(existing)
        run_request = RunRequest(
            request_id=request.request_id,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            input_text=request.input_text,
            metadata=_json_object(
                {"workflow_id": request.workflow_id}
                if request.workflow_id is not None
                else {}
            ),
        )
        run_id = self.id_generator.new_run_id()
        budget_state = self.budget_guard.start(self.budget, now_epoch_ms=self.clock.now_epoch_ms())
        record = RunRecord(run_id, run_request, RunStatus.CREATED, None, self.budget, budget_state, UsageSnapshot(), 1)
        try:
            await self.repository.create(record)
        except Exception as error:  # noqa: BLE001 - 并发幂等竞争需读取已存在 Run
            current = await self.repository.get_by_request_id(request.request_id, request.tenant_id)
            if current is not None:
                return self._view(current)
            raise normalize_error(error)
        await self._event(record, "run_created")
        record = await self._transition(record, RunStatus.QUEUED)
        await self._event(record, "run_queued")
        try:
            selection = self.router.select(request)
            await self._event(record, "strategy_selected", {"strategy": selection.mode.value, "rule_version": selection.rule_version, "reason_code": selection.reason_code})
            payload = _json_object(request.strategy_payload)
            registration = getattr(self.graph_runtime, "registry", None)
            registration = registration.get(selection.mode) if registration is not None else None
            if registration is not None:
                validate_strategy_payload(registration.strategy_payload_schema_version, payload, registration.allowed_strategy_payload_keys)
                adapted = registration.payload_adapter.adapt(registration.strategy_payload_schema_version, payload)
                if not isinstance(adapted, StrategyPayload):
                    adapted = StrategyPayload(registration.strategy_payload_schema_version, payload)
            else:
                adapted = StrategyPayload(request.strategy_payload_schema_version, payload)
            record = await self._transition(record, RunStatus.RUNNING, strategy=selection.mode)
            await self._event(record, "run_started")
            state: dict[str, object] = {
                "run_id": record.run_id,
                "tenant_id": request.tenant_id,
                "user_id": request.user_id,
                "request_id": request.request_id,
                "input_text": request.input_text,
                "strategy": selection.mode.value,
                "workflow_id": request.workflow_id,
                "strategy_payload_schema_version": adapted.schema_version,
                "strategy_payload": adapted.data,
                "allowed_tools": [],
                "estimated_input_tokens": 0,
                "prompt_id": None,
                "tool_output": None,
                "model_attempts": [],
                "runtime_facts": [],
                "usage": {},
                "budget_state": _budget_dict(record.budget_state),
                "output": None,
                "error_code": None,
                "degraded": False,
            }
            result = await self.graph_runtime.execute(selection, state)
            return await self._apply_graph_result(record, result)
        except HarnessError:
            raise
        except Exception as error:  # noqa: BLE001 - 图或适配器异常不得外泄
            failure = RunFailure(getattr(error, "code", "GRAPH_EXECUTION_FAILED"), "runtime", False, "运行执行失败")
            if record.status is not RunStatus.RUNNING:
                record = await self._transition(record, RunStatus.RUNNING, strategy=getattr(locals().get("selection", None), "mode", None))
            result = GraphExecutionResult(UsageSnapshot(), record.budget_state, CheckpointView(record.run_id, "s2:unknown:1", "cp-error"), (), RunStatus.FAILED, None, failure)
            return await self._apply_graph_result(record, result)

    async def _apply_graph_result(self, record: RunRecord, result: GraphExecutionResult) -> RunViewV1:
        """先记录 Checkpoint，再以 CAS 写 Run，最后公开终态事件。"""

        if not isinstance(result, GraphExecutionResult):
            raise HarnessError("GRAPH_EXECUTION_FAILED", "运行执行失败")
        target = result.next_status
        if target not in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.TIMED_OUT, RunStatus.WAITING_INPUT}:
            target = RunStatus.FAILED
            result = replace(result, failure=RunFailure("GRAPH_NEXT_STATUS_FORBIDDEN", "runtime", False, "图状态不被允许"), output=None)
        await self._event(record, "checkpoint_saved", {"checkpoint_id": result.checkpoint.checkpoint_id})
        next_record = record.transition(
            target,
            output=result.output,
            failure=result.failure,
            checkpoint_id=result.checkpoint.checkpoint_id,
            usage=result.usage,
            budget_state=result.budget_state,
            degraded=result.degraded,
        )
        await self.repository.save(next_record, record.version)
        terminal_event = {
            RunStatus.SUCCEEDED: "run_succeeded",
            RunStatus.FAILED: "run_failed",
            RunStatus.CANCELLED: "run_cancelled",
            RunStatus.TIMED_OUT: "run_timed_out",
            RunStatus.WAITING_INPUT: "run_waiting_input",
        }[target]
        if result.failure is not None and result.failure.code == "BUDGET_EXHAUSTED":
            await self._event(next_record, "budget_exhausted")
        await self._event(next_record, terminal_event)
        return self._view(next_record)

    async def get_run(self, run_id: str, tenant_id: str) -> RunViewV1:
        """按租户安全查询 Run。"""

        record = await self.repository.get(run_id, tenant_id)
        if record is None:
            raise HarnessError("RUN_NOT_FOUND", "Run 不存在", category="request")
        return self._view(record)

    async def resume_run(self, run_id: str, request: ResumeRunRequestV1) -> RunViewV1:
        """校验原 Checkpoint 后在同一 Run 上恢复。"""

        record = await self.repository.get(run_id, request.tenant_id)
        if record is None:
            raise HarnessError("RUN_NOT_FOUND", "Run 不存在", category="request")
        if record.status is not RunStatus.WAITING_INPUT:
            raise HarnessError("RUN_NOT_WAITING_INPUT", "Run 当前不等待补充输入")
        if record.strategy is None:
            raise HarnessError("CHECKPOINT_MISMATCH", "Checkpoint 不匹配")
        workflow_id = None
        if isinstance(record.request.metadata, JsonObject):
            metadata = dict(record.request.metadata.items)
            candidate_workflow = metadata.get("workflow_id")
            if isinstance(candidate_workflow, str):
                workflow_id = candidate_workflow
        selection = self.router.select(
            type(
                "Request",
                (),
                {
                    "requested_strategy": record.strategy,
                    "workflow_id": workflow_id,
                },
            )()
        )
        checkpoint = await self.graph_runtime.get_checkpoint(selection, run_id)
        if checkpoint is None or checkpoint.checkpoint_id != request.checkpoint_id or checkpoint.thread_id != run_id:
            raise HarnessError("CHECKPOINT_MISMATCH", "Checkpoint 不匹配")
        resume_value = _json_object(request.resume_value)
        try:
            self.graph_runtime.validate_resume(selection, checkpoint, resume_value)
        except Exception as error:
            raise HarnessError("RESUME_VALUE_INVALID", "恢复值无效") from error
        running = await self._transition(record, RunStatus.RUNNING)
        await self._event(running, "run_resumed", {"checkpoint_id": request.checkpoint_id})
        try:
            result = await self.graph_runtime.resume(selection, run_id, request.checkpoint_id, resume_value)
            if result.budget_state.started_at_epoch_ms != record.budget_state.started_at_epoch_ms or result.budget_state.deadline_epoch_ms != record.budget_state.deadline_epoch_ms:
                result = replace(result, budget_state=record.budget_state)
            return await self._apply_graph_result(running, result)
        except Exception as error:  # noqa: BLE001 - 恢复执行异常统一为安全错误
            failure = RunFailure(getattr(error, "code", "GRAPH_EXECUTION_FAILED"), "runtime", False, "运行执行失败")
            result = GraphExecutionResult(UsageSnapshot(), record.budget_state, checkpoint, (), RunStatus.FAILED, None, failure)
            return await self._apply_graph_result(running, result)

    async def cancel_run(self, run_id: str, request: CancelRunRequestV1) -> RunViewV1:
        """请求协作取消，并确保取消事件幂等。"""

        record = await self.repository.get(run_id, request.tenant_id)
        if record is None:
            raise HarnessError("RUN_NOT_FOUND", "Run 不存在", category="request")
        if record.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.TIMED_OUT}:
            if record.status is RunStatus.CANCELLED:
                return self._view(record)
            raise HarnessError("RUN_ALREADY_TERMINAL", "Run 已经结束")
        if run_id not in self._cancelled_runs:
            self._cancelled_runs.add(run_id)
            if self.cancellation_signal is not None:
                await self.cancellation_signal.request(run_id)
            await self._event(record, "run_cancel_requested", {"reason_code": request.reason_code})
        if record.status is RunStatus.WAITING_INPUT:
            cancelled = await self._transition(record, RunStatus.CANCELLED)
            await self._event(cancelled, "run_cancelled")
            return self._view(cancelled)
        return self._view(record)

    async def list_events(self, run_id: str, tenant_id: str, after_sequence: int = 0) -> Sequence[RunEventV1]:
        """按租户回放事件，并映射到公开版本化契约。"""

        if await self.repository.get(run_id, tenant_id) is None:
            raise HarnessError("RUN_NOT_FOUND", "Run 不存在", category="request")
        events = await self.event_store.list_after(run_id, tenant_id, after_sequence)
        return tuple(
            RunEventV1(
                event_id=event.event_id,
                event_type=cast(EventType, event.event_type),
                run_id=event.run_id,
                sequence=event.sequence,
                occurred_at_epoch_ms=event.occurred_at_epoch_ms,
                status=event.status,
                payload=_plain(event.payload),
            )
            for event in events
        )

    async def _transition(self, record: RunRecord, target: RunStatus, **kwargs: Any) -> RunRecord:
        next_record = record.transition(target, **kwargs)
        if next_record is record:
            return record
        await self.repository.save(next_record, record.version)
        return next_record

    async def _event(self, record: RunRecord, event_type: str, payload: Mapping[str, Any] | None = None) -> None:
        """在进程锁内按最后序号追加单调事件。"""

        async with self._event_lock:
            prior = await self.event_store.list_after(record.run_id, record.request.tenant_id, 0)
            sequence = prior[-1].sequence + 1 if prior else 1
            event = RunEventRecord(
                self.id_generator.new_event_id(),
                event_type,
                record.run_id,
                record.request.tenant_id,
                sequence,
                max(1, self.clock.now_epoch_ms()),
                record.status,
                _json_object(payload or {}),
            )
            await self.event_store.append(event)

    def _view(self, record: RunRecord) -> RunViewV1:
        """将内部 Run 快照映射为不含正文治理字段的公开视图。"""

        error = None
        if record.failure is not None:
            error = RunErrorV1(code=record.failure.code, category=record.failure.category, retryable=record.failure.retryable, safe_message=record.failure.safe_message)
        checkpoint = None
        if record.checkpoint_id is not None and record.strategy is not None:
            checkpoint = CheckpointViewV1(thread_id=record.run_id, checkpoint_ns=f"s2:{record.strategy.value}:1", checkpoint_id=record.checkpoint_id)
        return RunViewV1(
            run_id=record.run_id,
            request_id=record.request.request_id,
            status=record.status,
            strategy=record.strategy,
            output=_plain(record.output),
            error=error,
            usage=UsageV1(input_tokens=record.usage.input_tokens, output_tokens=record.usage.output_tokens, cost_microunits=record.usage.cost_microunits, estimated=record.usage.estimated),
            checkpoint=checkpoint,
            degraded=record.degraded,
        )


__all__ = ["AgentRuntimeService"]
