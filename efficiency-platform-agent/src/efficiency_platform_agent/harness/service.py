"""统一 Harness 生命周期：请求、Run、Graph、Checkpoint 与事件。"""

from __future__ import annotations

import asyncio
import copy
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, cast

from efficiency_platform_agent.contracts.deliverables import (
    DeliverableSetV1,
    DeliverableSetV2,
)
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
from efficiency_platform_agent.contracts.stream_events import (
    OperationVisiblePhase,
    StreamEventName,
)
from efficiency_platform_agent.core.budget import (
    BudgetCharge,
    BudgetExhaustedError,
    BudgetGuard,
    BudgetState,
    RemainingBudget,
)
from efficiency_platform_agent.core.diagnostics import (
    DiagnosticLevel,
    DiagnosticRecord,
    DiagnosticRecorderPort,
    NoopDiagnosticRecorder,
    bind_diagnostic_context,
    safe_exception_location,
)
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
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
from efficiency_platform_agent.runtime.event_hub import EventHub
from efficiency_platform_agent.runtime.operation_progress import (
    bind_operation_progress,
)

from .errors import HarnessError, normalize_error


@dataclass(frozen=True, slots=True)
class RunPipelinePreparation:
    """后台准备阶段交还给唯一 Run 生命周期的数据。"""

    request: CreateRunRequestV1
    stream_events: Sequence[tuple[StreamEventName, Mapping[str, Any]]] = ()
    usage: UsageSnapshot = field(default_factory=UsageSnapshot)
    degraded: bool = False
    charge: BudgetCharge = field(default_factory=BudgetCharge)

    def __post_init__(self) -> None:
        if not isinstance(self.charge, BudgetCharge):
            raise TypeError("charge 必须是 BudgetCharge")
        if (
            self.charge.input_tokens != self.usage.input_tokens
            or self.charge.output_tokens != self.usage.output_tokens
            or self.charge.cost_microunits != self.usage.cost_microunits
        ):
            raise ValueError("charge 必须与 usage 的模型用量一致")


@dataclass(frozen=True, slots=True)
class RunPipelineContext:
    """绑定到单个 Run 的后台准备预算与取消查询。"""

    run_id: str
    remaining_budget: RemainingBudget
    is_cancelled: Callable[[], Awaitable[bool]]
    wait_cancelled: Callable[[], Awaitable[None]]


def _json_object(value: Mapping[str, Any]) -> JsonObject:
    """深拷贝并转换为不可变 JsonObject。"""

    def convert(item: Any) -> JsonValue:
        if isinstance(item, Mapping):
            return JsonObject(
                tuple(
                    (str(key), convert(child))
                    for key, child in copy.deepcopy(dict(item)).items()
                )
            )
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
        event_hub: EventHub | None = None,
        output_streamer: Callable[[str, Mapping[str, Any]], AsyncIterator[str]]
        | None = None,
        diagnostic_recorder: DiagnosticRecorderPort | None = None,
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
        self.event_hub = event_hub or EventHub()
        self.output_streamer = output_streamer
        self.diagnostic_recorder = diagnostic_recorder or NoopDiagnosticRecorder()
        self._event_lock = asyncio.Lock()
        self._run_state_lock = asyncio.Lock()
        self._cancelled_runs: set[str] = set()
        self._background_tasks: set[asyncio.Task[RunViewV1 | None]] = set()
        self._realtime_output_run_tenants: dict[str, str] = {}
        self._realtime_output_runs: set[str] = set()
        self._assistant_started_runs: set[str] = set()
        self._published_operation_phases: dict[str, set[OperationVisiblePhase]] = {}
        self._run_event_listeners: list[
            Callable[[RunEventRecord], Awaitable[None]]
        ] = []
        self._run_state_listeners: list[Callable[[RunViewV1], Awaitable[None]]] = []
        self._pipeline_usage: dict[str, UsageSnapshot] = {}

    def add_run_event_listener(
        self, listener: Callable[[RunEventRecord], Awaitable[None]]
    ) -> None:
        """登记已持久化 Run 事件的轻量观察者。"""
        if not callable(listener):
            raise TypeError("listener 必须可调用")
        self._run_event_listeners.append(listener)

    def add_run_state_listener(
        self, listener: Callable[[RunViewV1], Awaitable[None]]
    ) -> None:
        """登记 Run 状态观察者，用于组合根释放临时关联。"""
        if not callable(listener):
            raise TypeError("listener 必须可调用")
        self._run_state_listeners.append(listener)

    async def create_and_execute(self, request: CreateRunRequestV1) -> RunViewV1:
        """保留同步兼容路径：创建、排队并在当前协程执行 Graph。"""

        record, created = await self._create_queued(request)
        if not created:
            return self._view(record)
        return await self._execute_queued(record, request)

    async def create_and_schedule(
        self,
        request: CreateRunRequestV1,
        *,
        initial_stream_events: Sequence[tuple[StreamEventName, Mapping[str, Any]]] = (),
    ) -> RunViewV1:
        """创建并排队 Run，在后台协程执行且立即返回 queued 视图。"""

        record, created = await self._create_queued(request)
        if not created:
            return self._view(record)
        for name, payload in initial_stream_events:
            await self.event_hub.publish_next(record.run_id, name, payload)
        task = asyncio.create_task(
            self._execute_background(record, request),
            name=f"agent-run:{record.run_id}",
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._discard_background_task)
        return self._view(record)

    async def create_and_schedule_pipeline(
        self,
        request: CreateRunRequestV1,
        prepare: Callable[[RunPipelineContext], Awaitable[RunPipelinePreparation]],
        *,
        on_queued: Callable[[RunViewV1], Awaitable[None]] | None = None,
    ) -> RunViewV1:
        """先创建 queued Run，再在后台完成模型准备和 Graph 执行。"""
        if not callable(prepare):
            raise TypeError("prepare 必须可调用")
        record, created = await self._create_queued(request)
        view = self._view(record)
        if on_queued is not None:
            await on_queued(view)
        if not created:
            if record.status in {
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }:
                await self._notify_run_state(view)
            return view
        task = asyncio.create_task(
            self._execute_pipeline_background(record, request, prepare),
            name=f"agent-run-pipeline:{record.run_id}",
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._discard_background_task)
        return view

    async def _execute_pipeline_background(
        self,
        record: RunRecord,
        original: CreateRunRequestV1,
        prepare: Callable[[RunPipelineContext], Awaitable[RunPipelinePreparation]],
    ) -> RunViewV1 | None:
        """把模型准备错误归一化到已经创建的同一个 Run。"""
        with bind_diagnostic_context(
            run_id=record.run_id, request_id=original.request_id
        ):
            try:
                return await self._prepare_and_execute_pipeline(
                    record, original, prepare
                )
            except Exception as error:  # noqa: BLE001 - 准备阶段不得泄露模型异常
                self._record_exception(
                    "pipeline_preparation_failed", "PIPELINE_PREPARATION_FAILED", error
                )
                return await self._settle_background_failure(record, original, error)

    async def _prepare_and_execute_pipeline(
        self,
        record: RunRecord,
        original: CreateRunRequestV1,
        prepare: Callable[[RunPipelineContext], Awaitable[RunPipelinePreparation]],
    ) -> RunViewV1 | None:
        """完成 Pipeline 准备，并交由已有后台图执行路径处理。"""

        remaining = self.budget_guard.check_before_node(
            record.budget,
            record.budget_state,
            BudgetCharge(iterations=1),
            now_epoch_ms=self.clock.now_epoch_ms(),
        )
        if await self._is_cancelled(record.run_id):
            raise HarnessError("CANCELLED", "运行已取消", category="runtime")
        prepared = await prepare(
            RunPipelineContext(
                record.run_id,
                remaining,
                lambda: self._is_cancelled(record.run_id),
                lambda: self._wait_cancelled(record.run_id),
            )
        )
        if not isinstance(prepared, RunPipelinePreparation):
            raise TypeError("pipeline 准备结果无效")
        request = prepared.request
        if (
            request.request_id != original.request_id
            or request.tenant_id != original.tenant_id
            or request.user_id != original.user_id
            or request.input_text != original.input_text
        ):
            raise ValueError("PIPELINE_IDENTITY_MISMATCH")
        current = await self.repository.get(record.run_id, original.tenant_id)
        if current is None:
            return None
        try:
            next_budget, _ = self.budget_guard.record_after_node(
                current.budget,
                current.budget_state,
                prepared.charge,
                now_epoch_ms=self.clock.now_epoch_ms(),
            )
        except BudgetExhaustedError as error:
            cast(Any, error).usage = prepared.usage
            cast(Any, error).degraded = prepared.degraded
            cast(Any, error).charge = prepared.charge
            raise
        enriched = replace(
            current,
            usage=prepared.usage,
            budget_state=next_budget,
            degraded=prepared.degraded,
            version=current.version + 1,
        )
        await self.repository.save(enriched, current.version)
        record = enriched
        self._pipeline_usage[record.run_id] = prepared.usage
        if record.status is RunStatus.CANCELLED or await self._is_cancelled(
            record.run_id
        ):
            self._pipeline_usage.pop(record.run_id, None)
            return self._view(record)
        for name, payload in prepared.stream_events:
            await self.event_hub.publish_next(record.run_id, name, payload)
        return await self._execute_background(record, request)

    async def _settle_background_failure(
        self,
        record: RunRecord,
        request: CreateRunRequestV1,
        error: Exception,
    ) -> RunViewV1 | None:
        """把后台准备或执行异常写回同一 Run。"""
        current = await self.repository.get(record.run_id, request.tenant_id)
        if current is None:
            return None
        code = getattr(error, "code", "PIPELINE_PREPARATION_FAILED")
        usage = getattr(error, "usage", UsageSnapshot())
        if not isinstance(usage, UsageSnapshot):
            usage = UsageSnapshot()
        degraded = bool(getattr(error, "degraded", False))
        charge = self._pipeline_charge_from_error(error, usage)
        if current.status in {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
        }:
            if current.status is RunStatus.CANCELLED and (
                usage != UsageSnapshot() or degraded or charge != BudgetCharge()
            ):
                try:
                    next_budget, _ = self.budget_guard.record_after_node(
                        current.budget,
                        current.budget_state,
                        charge,
                        now_epoch_ms=self.clock.now_epoch_ms(),
                    )
                except BudgetExhaustedError:
                    next_budget = self._budget_state_after_pipeline(
                        current.budget_state,
                        charge,
                    )
                revised = replace(
                    current,
                    usage=usage,
                    budget_state=next_budget,
                    degraded=current.degraded or degraded,
                    version=current.version + 1,
                )
                await self.repository.save(revised, current.version)
                current = revised
            return self._view(current)
        if current.status is not RunStatus.RUNNING:
            current = await self._transition(current, RunStatus.RUNNING)
            await self._event(current, "run_started")
        target = RunStatus.FAILED
        safe_message = getattr(error, "safe_message", "运行执行失败")
        if code == "BUDGET_EXHAUSTED":
            target = RunStatus.TIMED_OUT
            safe_message = "运行预算已耗尽"
        elif code in {"CANCELLED", "RUN_CANCELLED"}:
            target = RunStatus.CANCELLED
            safe_message = "运行已取消"
        if usage != UsageSnapshot() or degraded or charge != BudgetCharge():
            try:
                next_budget, _ = self.budget_guard.record_after_node(
                    current.budget,
                    current.budget_state,
                    charge,
                    now_epoch_ms=self.clock.now_epoch_ms(),
                )
            except BudgetExhaustedError:
                target = RunStatus.TIMED_OUT
                code = "BUDGET_EXHAUSTED"
                safe_message = "运行预算已耗尽"
                next_budget = self._budget_state_after_pipeline(
                    current.budget_state,
                    charge,
                )
            current = replace(
                current,
                usage=usage,
                budget_state=next_budget,
                degraded=current.degraded or degraded,
                version=current.version + 1,
            )
            await self.repository.save(current, current.version - 1)
            if target is not RunStatus.CANCELLED:
                await self.event_hub.publish_next(
                    current.run_id,
                    "usage_update",
                    {
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "cost_microunits": usage.cost_microunits,
                        "estimated": usage.estimated,
                        "degraded": degraded,
                    },
                )
        failure = RunFailure(
            str(code),
            getattr(error, "category", "runtime"),
            bool(getattr(error, "retryable", False)),
            str(safe_message),
        )
        result = GraphExecutionResult(
            usage,
            current.budget_state,
            CheckpointView(current.run_id, "s2:unknown:1", "cp-error"),
            (),
            target,
            None,
            None if target is RunStatus.CANCELLED else failure,
            degraded=current.degraded or degraded,
        )
        return await self._apply_graph_result(current, result)

    async def _is_cancelled(self, run_id: str) -> bool:
        """以 Run 标识查询取消信号；无信号时返回否。"""
        if run_id in self._cancelled_runs:
            return True
        probe = getattr(self.cancellation_signal, "is_requested", None)
        if not callable(probe):
            return False
        return bool(await probe(run_id))

    async def _wait_cancelled(self, run_id: str) -> None:
        """等待指定 Run 的取消信号；无等待端口时保持挂起。"""
        if run_id in self._cancelled_runs:
            return
        waiter = getattr(self.cancellation_signal, "wait_requested", None)
        if callable(waiter):
            await waiter(run_id)
            return
        await asyncio.Event().wait()

    @staticmethod
    def _pipeline_charge_from_error(
        error: Exception, usage: UsageSnapshot
    ) -> BudgetCharge:
        """优先使用准备异常携带的实际消耗，兼容旧异常的 attempts。"""
        charge = getattr(error, "charge", None)
        if isinstance(charge, BudgetCharge):
            return charge
        attempts = getattr(error, "attempts", ())
        count = len(attempts) if isinstance(attempts, tuple) else 0
        return BudgetCharge(
            iterations=count,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_microunits=usage.cost_microunits,
        )

    @staticmethod
    def _budget_state_after_pipeline(
        state: BudgetState, charge: BudgetCharge
    ) -> BudgetState:
        """预算超限时仍记录已发生的真实消耗，随后失败关闭。"""
        consumed = state.consumed
        return BudgetState(
            BudgetCharge(
                iterations=consumed.iterations + charge.iterations,
                tool_calls=consumed.tool_calls,
                input_tokens=consumed.input_tokens + charge.input_tokens,
                output_tokens=consumed.output_tokens + charge.output_tokens,
                cost_microunits=(consumed.cost_microunits + charge.cost_microunits),
            ),
            state.started_at_epoch_ms,
            state.deadline_epoch_ms,
        )

    async def wait_for_background_tasks(self) -> None:
        """等待当前后台 Run 收敛，供应用关闭与离线测试使用。"""

        tasks = tuple(self._background_tasks)
        if tasks:
            await asyncio.gather(*tasks)

    async def _create_queued(
        self, request: CreateRunRequestV1
    ) -> tuple[RunRecord, bool]:
        """按幂等键创建 Run 并完成 CREATED 到 QUEUED 的持久化。"""

        if not isinstance(request, CreateRunRequestV1):
            raise HarnessError("INVALID_REQUEST", "创建请求无效", category="request")
        existing = await self.repository.get_by_request_id(
            request.request_id, request.tenant_id
        )
        if existing is not None:
            return existing, False
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
        budget_state = self.budget_guard.start(
            self.budget, now_epoch_ms=self.clock.now_epoch_ms()
        )
        record = RunRecord(
            run_id,
            run_request,
            RunStatus.CREATED,
            None,
            self.budget,
            budget_state,
            UsageSnapshot(),
            1,
        )
        try:
            await self.repository.create(record)
        except Exception as error:  # noqa: BLE001 - 并发幂等竞争需读取已存在 Run
            current = await self.repository.get_by_request_id(
                request.request_id, request.tenant_id
            )
            if current is not None:
                return current, False
            raise normalize_error(error)
        await self._event(record, "run_created")
        record = await self._transition(record, RunStatus.QUEUED)
        await self._event(record, "run_queued")
        return record, True

    async def _execute_background(
        self, record: RunRecord, request: CreateRunRequestV1
    ) -> RunViewV1 | None:
        """执行已排队 Run，并将后台边界异常归一化为失败状态。"""

        with bind_diagnostic_context(
            run_id=record.run_id, request_id=request.request_id
        ):
            try:
                return await self._execute_queued(record, request)
            except Exception as error:  # noqa: BLE001 - 后台任务不得泄露未观察异常
                current = await self.repository.get(record.run_id, request.tenant_id)
                self._record_exception(
                    "background_execution_failed",
                    getattr(error, "code", "BACKGROUND_EXECUTION_FAILED"),
                    error,
                    stage="background.execute",
                    strategy=(
                        current.strategy if current is not None else record.strategy
                    ),
                )
                return await self._settle_background_failure(record, request, error)

    async def _execute_queued(
        self, record: RunRecord, request: CreateRunRequestV1
    ) -> RunViewV1:
        """复用唯一 Graph Runtime 执行一个已经进入 QUEUED 的 Run。"""

        with bind_diagnostic_context(
            run_id=record.run_id, request_id=request.request_id
        ):
            return await self._execute_queued_with_context(record, request)

    async def _publish_bound_operation_progress(
        self,
        run_id: str,
        event: StreamEventName,
        phase: OperationVisiblePhase,
        payload: Mapping[str, Any],
    ) -> None:
        """只发布当前 Run 真实节点报告的安全阶段，并对开始事件去重。"""

        if event == "phase_started":
            published = self._published_operation_phases.setdefault(run_id, set())
            if phase in published:
                return
            published.add(phase)
        await self.event_hub.publish_next(
            run_id, event, {**dict(payload), "phase": phase}
        )

    async def _execute_queued_with_context(
        self, record: RunRecord, request: CreateRunRequestV1
    ) -> RunViewV1:
        """在已关联诊断上下文中执行原有 Graph 生命周期。"""

        current = await self.repository.get(record.run_id, request.tenant_id)
        if current is None:
            raise HarnessError("RUN_NOT_FOUND", "Run 不存在", category="request")
        if current.status in {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
        }:
            return self._view(current)
        record = current
        try:
            selection = self.router.select(request)
            with bind_diagnostic_context(strategy=selection.mode.value):
                self._record(
                    DiagnosticRecord(
                        event_name="strategy_selected",
                        component="run",
                        level=DiagnosticLevel.INFO,
                        stage="routing.select",
                        reason_code=selection.reason_code,
                        rule_version=selection.rule_version,
                    )
                )
            await self._event(
                record,
                "strategy_selected",
                {
                    "strategy": selection.mode.value,
                    "rule_version": selection.rule_version,
                    "reason_code": selection.reason_code,
                },
            )
            payload = _json_object(request.strategy_payload)
            registration = getattr(self.graph_runtime, "registry", None)
            registration = (
                registration.get(selection.mode) if registration is not None else None
            )
            if registration is not None:
                validate_strategy_payload(
                    registration.strategy_payload_schema_version,
                    payload,
                    registration.allowed_strategy_payload_keys,
                )
                adapted = registration.payload_adapter.adapt(
                    registration.strategy_payload_schema_version, payload
                )
                if not isinstance(adapted, StrategyPayload):
                    adapted = StrategyPayload(
                        registration.strategy_payload_schema_version, payload
                    )
            else:
                adapted = StrategyPayload(
                    request.strategy_payload_schema_version, payload
                )
            record = await self._transition(
                record, RunStatus.RUNNING, strategy=selection.mode
            )
            self._realtime_output_run_tenants[record.run_id] = request.tenant_id
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
                "test_mode": getattr(self, "_test_mode", None),
                "next_status": None,
            }
            with bind_diagnostic_context(strategy=selection.mode.value):

                async def publish_progress(
                    event: StreamEventName,
                    phase: OperationVisiblePhase,
                    payload: Mapping[str, Any],
                ) -> None:
                    await self._publish_bound_operation_progress(
                        record.run_id, event, phase, payload
                    )

                with bind_operation_progress(publish_progress):
                    result = await self.graph_runtime.execute(selection, state)
                # 取消请求一旦被受理，晚到的图结果不得覆盖取消终态。
                if await self._is_cancelled(record.run_id) and isinstance(
                    result, GraphExecutionResult
                ):
                    result = replace(
                        result,
                        next_status=RunStatus.CANCELLED,
                        output=None,
                        failure=None,
                    )
                if (
                    result.budget_state.started_at_epoch_ms
                    != record.budget_state.started_at_epoch_ms
                    or result.budget_state.deadline_epoch_ms
                    != record.budget_state.deadline_epoch_ms
                ):
                    result = replace(result, budget_state=record.budget_state)
                return await self._apply_graph_result(record, result)
        except HarnessError:
            raise
        except Exception as error:  # noqa: BLE001 - 图或适配器异常不得外泄
            self._record_exception(
                "graph_execution_failed",
                getattr(error, "code", "GRAPH_EXECUTION_FAILED"),
                error,
                strategy=getattr(locals().get("selection", None), "mode", None),
            )
            current = await self.repository.get(record.run_id, request.tenant_id)
            if current is not None and current.status in {
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }:
                return self._view(current)
            if current is not None:
                record = current
            failure = RunFailure(
                getattr(error, "code", "GRAPH_EXECUTION_FAILED"),
                "runtime",
                False,
                "运行执行失败",
            )
            if record.status is not RunStatus.RUNNING:
                record = await self._transition(
                    record,
                    RunStatus.RUNNING,
                    strategy=getattr(locals().get("selection", None), "mode", None),
                )
            result = GraphExecutionResult(
                UsageSnapshot(),
                record.budget_state,
                CheckpointView(record.run_id, "s2:unknown:1", "cp-error"),
                (),
                RunStatus.FAILED,
                None,
                failure,
            )
            return await self._apply_graph_result(record, result)

    def _record_exception(
        self,
        event_name: str,
        error_code: object,
        error: BaseException,
        *,
        stage: str | None = None,
        strategy: StrategyMode | None = None,
    ) -> None:
        """记录 Harness 吞异常边界的白名单诊断事实。"""

        record = DiagnosticRecord(
            event_name=event_name,
            component=(
                "graph"
                if event_name in {"graph_execution_failed", "graph_resume_failed"}
                else "run"
            ),
            level=DiagnosticLevel.ERROR,
            stage=(
                stage
                or (
                    "graph.execute"
                    if event_name == "graph_execution_failed"
                    else "pipeline.prepare"
                )
            ),
            error_code=str(error_code),
            error_type=type(error).__name__,
            error_location=safe_exception_location(error),
            retryable=False,
        )
        if strategy is None:
            self._record(record)
            return
        with bind_diagnostic_context(strategy=strategy.value):
            self._record(record)

    def _record(self, record: DiagnosticRecord) -> None:
        """隔离 Recorder 失败，避免日志影响 Run 终态。"""

        try:
            self.diagnostic_recorder.record(record)
        except Exception:  # noqa: BLE001 - Recorder 异常不得影响 Run 终态
            return

    def _discard_background_task(self, task: asyncio.Task[RunViewV1 | None]) -> None:
        """释放后台任务引用；异常已在后台边界内部归一化。"""

        self._background_tasks.discard(task)

    async def _apply_graph_result(
        self, record: RunRecord, result: GraphExecutionResult
    ) -> RunViewV1:
        """先记录 Checkpoint，再以 CAS 写 Run，最后公开终态事件。"""

        if not isinstance(result, GraphExecutionResult):
            raise HarnessError("GRAPH_EXECUTION_FAILED", "运行执行失败")
        target = result.next_status
        if target not in {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
            RunStatus.WAITING_INPUT,
        }:
            target = RunStatus.FAILED
            result = replace(
                result,
                failure=RunFailure(
                    "GRAPH_NEXT_STATUS_FORBIDDEN", "runtime", False, "图状态不被允许"
                ),
                output=None,
            )
        async with self._run_state_lock:
            current = await self.repository.get(record.run_id, record.request.tenant_id)
            if current is None:
                raise HarnessError("RUN_NOT_FOUND", "Run 不存在", category="request")
            if current.status in {
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }:
                return self._view(current)
            record = current
            if await self._is_cancelled(record.run_id):
                target = RunStatus.CANCELLED
                result = replace(
                    result,
                    next_status=RunStatus.CANCELLED,
                    output=None,
                    failure=None,
                )
            prefix = self._pipeline_usage.get(record.run_id)
            combined_usage = result.usage
            if prefix is not None:
                combined_usage = UsageSnapshot(
                    prefix.input_tokens + result.usage.input_tokens,
                    prefix.output_tokens + result.usage.output_tokens,
                    prefix.cost_microunits + result.usage.cost_microunits,
                    prefix.estimated or result.usage.estimated,
                )
            next_record = record.transition(
                target,
                output=result.output,
                failure=result.failure,
                checkpoint_id=result.checkpoint.checkpoint_id,
                usage=combined_usage,
                budget_state=result.budget_state,
                degraded=record.degraded or result.degraded,
            )
            await self.repository.save(next_record, record.version)
        # 只有 Run CAS 成功后，才公开 Checkpoint 已保存事实。
        await self._event(
            next_record,
            "checkpoint_saved",
            {"checkpoint_id": result.checkpoint.checkpoint_id},
        )
        terminal_event = {
            RunStatus.SUCCEEDED: "run_succeeded",
            RunStatus.FAILED: "run_failed",
            RunStatus.CANCELLED: "run_cancelled",
            RunStatus.TIMED_OUT: "run_timed_out",
            RunStatus.WAITING_INPUT: "run_waiting_input",
        }[target]
        if result.failure is not None and result.failure.code == "BUDGET_EXHAUSTED":
            await self._event(next_record, "budget_exhausted")
        if target is RunStatus.SUCCEEDED:
            presentation_degraded = await self._publish_result_events(next_record)
            if presentation_degraded and not next_record.degraded:
                revised = replace(
                    next_record, degraded=True, version=next_record.version + 1
                )
                await self.repository.save(revised, next_record.version)
                next_record = revised
        await self._event(next_record, terminal_event)
        view = self._view(next_record)
        await self._notify_run_state(view)
        self._realtime_output_run_tenants.pop(record.run_id, None)
        self._realtime_output_runs.discard(record.run_id)
        self._assistant_started_runs.discard(record.run_id)
        if target is not RunStatus.WAITING_INPUT:
            self._pipeline_usage.pop(record.run_id, None)
            self._published_operation_phases.pop(record.run_id, None)
        return view

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
        with bind_diagnostic_context(
            run_id=run_id,
            request_id=record.request.request_id,
            strategy=record.strategy.value,
        ):
            return await self._resume_run_with_context(record, request)

    async def _resume_run_with_context(
        self, record: RunRecord, request: ResumeRunRequestV1
    ) -> RunViewV1:
        """在原 Run 诊断上下文中验证并恢复 Checkpoint。"""

        run_id = record.run_id
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
        checkpoint = await self.graph_runtime.get_checkpoint(
            selection, run_id, tenant_id=request.tenant_id
        )
        if (
            checkpoint is None
            or checkpoint.checkpoint_id != request.checkpoint_id
            or checkpoint.thread_id != run_id
        ):
            raise HarnessError("CHECKPOINT_MISMATCH", "Checkpoint 不匹配")
        resume_value = _json_object(request.resume_value)
        try:
            self.graph_runtime.validate_resume(selection, checkpoint, resume_value)
        except Exception as error:
            raise HarnessError("RESUME_VALUE_INVALID", "恢复值无效") from error
        running = await self._transition(record, RunStatus.RUNNING)
        await self._event(
            running, "run_resumed", {"checkpoint_id": request.checkpoint_id}
        )
        try:
            result = await self.graph_runtime.resume(
                selection,
                run_id,
                request.checkpoint_id,
                resume_value,
                tenant_id=request.tenant_id,
            )
            # 恢复执行期间收到的取消请求同样优先于晚到的图结果。
            if await self._is_cancelled(run_id) and isinstance(
                result, GraphExecutionResult
            ):
                result = replace(
                    result,
                    next_status=RunStatus.CANCELLED,
                    output=None,
                    failure=None,
                )
            if (
                result.budget_state.started_at_epoch_ms
                != record.budget_state.started_at_epoch_ms
                or result.budget_state.deadline_epoch_ms
                != record.budget_state.deadline_epoch_ms
            ):
                result = replace(result, budget_state=record.budget_state)
            if getattr(self, "_test_mode", None) == "suspend":
                return self._view(running)
            return await self._apply_graph_result(running, result)
        except Exception as error:  # noqa: BLE001 - 恢复执行异常统一为安全错误
            self._record_exception(
                "graph_resume_failed",
                getattr(error, "code", "GRAPH_EXECUTION_FAILED"),
                error,
                stage="graph.resume",
                strategy=record.strategy,
            )
            failure = RunFailure(
                getattr(error, "code", "GRAPH_EXECUTION_FAILED"),
                "runtime",
                False,
                "运行执行失败",
            )
            result = GraphExecutionResult(
                UsageSnapshot(),
                record.budget_state,
                checkpoint,
                (),
                RunStatus.FAILED,
                None,
                failure,
            )
            return await self._apply_graph_result(running, result)

    async def cancel_run(self, run_id: str, request: CancelRunRequestV1) -> RunViewV1:
        """在线性化状态锁内受理取消，避免晚到结果覆盖取消。"""

        async with self._run_state_lock:
            return await self._cancel_run_locked(run_id, request)

    async def _cancel_run_locked(
        self, run_id: str, request: CancelRunRequestV1
    ) -> RunViewV1:
        """请求协作取消，并确保取消事件幂等。"""

        record = await self.repository.get(run_id, request.tenant_id)
        if record is None:
            raise HarnessError("RUN_NOT_FOUND", "Run 不存在", category="request")
        if record.status in {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
        }:
            if record.status is RunStatus.CANCELLED:
                return self._view(record)
            raise HarnessError("RUN_ALREADY_TERMINAL", "Run 已经结束")
        if run_id not in self._cancelled_runs:
            self._cancelled_runs.add(run_id)
            if self.cancellation_signal is not None:
                await self.cancellation_signal.request(run_id)
            await self._event(
                record, "run_cancel_requested", {"reason_code": request.reason_code}
            )
        if (
            record.status
            in {RunStatus.CREATED, RunStatus.QUEUED, RunStatus.WAITING_INPUT}
            or getattr(self, "_test_mode", None) == "suspend"
        ):
            cancelled = await self._transition(record, RunStatus.CANCELLED)
            await self._event(cancelled, "run_cancelled")
            view = self._view(cancelled)
            await self._notify_run_state(view)
            self._pipeline_usage.pop(run_id, None)
            return view
        return self._view(record)

    async def list_events(
        self, run_id: str, tenant_id: str, after_sequence: int = 0
    ) -> Sequence[RunEventV1]:
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

    async def _transition(
        self, record: RunRecord, target: RunStatus, **kwargs: Any
    ) -> RunRecord:
        next_record = record.transition(target, **kwargs)
        if next_record is record:
            return record
        await self.repository.save(next_record, record.version)
        return next_record

    async def _event(
        self,
        record: RunRecord,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        """在进程锁内按最后序号追加单调事件。"""

        async with self._event_lock:
            prior = await self.event_store.list_after(
                record.run_id, record.request.tenant_id, 0
            )
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
            await self._notify_run_event(event)
            await self._publish_stream_event(record, event_type, sequence)

    async def _publish_stream_event(
        self, record: RunRecord, event_type: str, sequence: int
    ) -> None:
        """将基础 Run 生命周期映射为对话流的开始、错误与终止事件。"""

        events: list[tuple[StreamEventName, dict[str, Any]]] = []
        if event_type == "run_started":
            events.append(("run_started", {"status": record.status.value}))
        elif event_type == "run_waiting_input":
            history = await self.event_hub.replay(record.run_id, 0)
            if not any(item.event == "clarification_required" for item in history):
                events.append(
                    ("clarification_required", {"status": record.status.value})
                )
        elif event_type in {"run_failed", "run_timed_out"}:
            failure = record.failure
            events.append(
                (
                    "stream_error",
                    {
                        "code": failure.code if failure is not None else "RUN_FAILED",
                        "category": (
                            failure.category if failure is not None else "runtime"
                        ),
                        "retryable": (
                            failure.retryable if failure is not None else False
                        ),
                        "safe_message": (
                            failure.safe_message
                            if failure is not None
                            else "运行执行失败"
                        ),
                    },
                )
            )
            events.append(
                (
                    "stream_done",
                    {
                        "status": record.status.value,
                        "degraded": record.degraded,
                    },
                )
            )
        elif event_type in {"run_succeeded", "run_cancelled"}:
            events.append(
                (
                    "stream_done",
                    {
                        "status": record.status.value,
                        "degraded": record.degraded,
                    },
                )
            )
        del sequence
        for name, payload in events:
            await self.event_hub.publish_next(record.run_id, name, payload)

    async def _publish_result_events(self, record: RunRecord) -> bool:
        """把安全可见正文和成品映射到同一个 Run 事件流。"""
        output = _plain(record.output)
        if not isinstance(output, Mapping):
            return False
        presentation_degraded = False
        content = output.get("content")
        already_streamed = (
            record.strategy is StrategyMode.DIRECT
            and record.run_id in self._realtime_output_runs
        )
        if isinstance(content, str) and content and not already_streamed:
            await self.event_hub.publish_next(record.run_id, "assistant_started", {})
            if self.output_streamer is None:
                await self.event_hub.publish_next(
                    record.run_id, "assistant_delta", {"delta": content}
                )
            else:
                emitted = False
                try:
                    async for delta in self.output_streamer(record.run_id, output):
                        if isinstance(delta, str) and delta:
                            emitted = True
                            await self.event_hub.publish_next(
                                record.run_id, "assistant_delta", {"delta": delta}
                            )
                except Exception:  # noqa: BLE001 - 流式呈现失败回退既有安全正文
                    presentation_degraded = True
                    await self.event_hub.publish_next(
                        record.run_id,
                        "stream_error",
                        {
                            "code": "OUTPUT_STREAM_INTERRUPTED",
                            "category": "presentation",
                            "retryable": False,
                            "safe_message": "流式输出中断，已补充完整结果",
                        },
                    )
                    fallback = content if not emitted else f"\n\n{content}"
                    await self.event_hub.publish_next(
                        record.run_id, "assistant_delta", {"delta": fallback}
                    )
        deliverable_set = output.get("deliverable_set")
        if isinstance(deliverable_set, Mapping):
            delivery_version = output.get("delivery_contract_version")
            if delivery_version is None:
                delivery_version = deliverable_set.get(
                    "contract_version", "deliverable-set/1"
                )
            try:
                if delivery_version == "deliverable-set/2":
                    validated = DeliverableSetV2.model_validate(
                        dict(deliverable_set)
                    ).model_dump(mode="json")
                elif delivery_version == "deliverable-set/1":
                    validated = DeliverableSetV1.model_validate(
                        dict(deliverable_set)
                    ).model_dump(mode="json")
                else:
                    raise ValueError("DELIVERABLE_SET_VERSION_UNSUPPORTED")
            except (TypeError, ValueError):
                await self.event_hub.publish_next(
                    record.run_id,
                    "stream_error",
                    {
                        "code": "DELIVERABLE_SET_INVALID",
                        "category": "presentation",
                        "retryable": False,
                        "safe_message": "交付结果校验失败",
                    },
                )
                return True
            await self.event_hub.publish_next(
                record.run_id,
                "deliverable",
                {"deliverable_set": validated},
            )
        return presentation_degraded

    async def publish_assistant_delta(self, run_id: str, delta: str) -> bool:
        """仅向仍在运行且未取消的 Run 发布已治理的实时正文。"""
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id必须是非空字符串")
        if not isinstance(delta, str):
            raise TypeError("delta必须是字符串")
        if not delta:
            return False
        async with self._run_state_lock:
            tenant_id = self._realtime_output_run_tenants.get(run_id)
            if tenant_id is None:
                return False
            record = await self.repository.get(run_id, tenant_id)
            if (
                record is None
                or record.status is not RunStatus.RUNNING
                or await self._is_cancelled(run_id)
            ):
                return False
            if run_id not in self._assistant_started_runs:
                self._assistant_started_runs.add(run_id)
                await self.event_hub.publish_next(run_id, "assistant_started", {})
            await self.event_hub.publish_next(
                run_id, "assistant_delta", {"delta": delta}
            )
            self._realtime_output_runs.add(run_id)
            return True

    async def _notify_run_state(self, view: RunViewV1) -> None:
        """串行通知轻量观察者；观察失败不得改写 Run 结果。"""
        for listener in tuple(self._run_state_listeners):
            try:
                await listener(view)
            except Exception as error:  # noqa: BLE001 - 清理失败不污染业务终态
                del error

    async def _notify_run_event(self, event: RunEventRecord) -> None:
        """按持久化顺序通知事件观察者；观察失败不污染 Run。"""
        for listener in tuple(self._run_event_listeners):
            try:
                await listener(event)
            except Exception as error:  # noqa: BLE001 - 日志失败不污染业务事件
                del error

    def _view(self, record: RunRecord) -> RunViewV1:
        """将内部 Run 快照映射为不含正文治理字段的公开视图。"""

        error = None
        if record.failure is not None:
            error = RunErrorV1(
                code=record.failure.code,
                category=record.failure.category,
                retryable=record.failure.retryable,
                safe_message=record.failure.safe_message,
            )
        checkpoint = None
        if record.checkpoint_id is not None and record.strategy is not None:
            checkpoint = CheckpointViewV1(
                thread_id=record.run_id,
                checkpoint_ns=f"s2:{record.strategy.value}:1",
                checkpoint_id=record.checkpoint_id,
            )
        return RunViewV1(
            run_id=record.run_id,
            request_id=record.request.request_id,
            status=record.status,
            strategy=record.strategy,
            output=_plain(record.output),
            error=error,
            usage=UsageV1(
                input_tokens=record.usage.input_tokens,
                output_tokens=record.usage.output_tokens,
                cost_microunits=record.usage.cost_microunits,
                estimated=record.usage.estimated,
            ),
            checkpoint=checkpoint,
            degraded=record.degraded,
            budget_deadline=record.budget_state.deadline_epoch_ms,
        )


__all__ = ["AgentRuntimeService", "RunPipelineContext", "RunPipelinePreparation"]
