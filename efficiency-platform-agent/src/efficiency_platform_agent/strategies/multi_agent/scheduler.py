"""中央 Supervisor 的有界波次调度器。"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Protocol, cast

from efficiency_platform_agent.agents.operation.supervisor.budget import BudgetLedger
from efficiency_platform_agent.agents.operation.supervisor.dispatch import (
    DispatchBuilder,
)
from efficiency_platform_agent.agents.operation.supervisor.selection import (
    SelectedSpecialist,
    SpecialistSelector,
)
from efficiency_platform_agent.core.diagnostics import (
    DiagnosticLevel,
    DiagnosticRecord,
    DiagnosticRecorderPort,
    NoopDiagnosticRecorder,
    safe_exception_location,
)
from efficiency_platform_agent.core.multi_agent import (
    BudgetUsage,
    TaskExecutionStatus,
    TaskOutcome,
)
from efficiency_platform_agent.core.run import (
    JsonObject,
    JsonValue,
    RunResult,
    SupervisorTask,
)

from .state import OperationSupervisorState, validate_supervisor_state


class _SelectorPort(Protocol):
    def rank(self, node: object) -> tuple[object, ...]: ...


class _FactoryPort(Protocol):
    def create(self, agent_id: str) -> object: ...


class _GraphPort(Protocol):
    tasks: tuple[object, ...]


class _LedgerPort(Protocol):
    def consume(self, task_id: str, usage: BudgetUsage) -> None: ...


class _ClockPort(Protocol):
    def now_epoch_ms(self) -> int: ...


class _NeverCancellationSignal:
    """策略层默认的永不触发取消替身，不依赖编排层实现。"""

    async def is_requested(self, run_id: str) -> bool:
        return False

    async def wait_requested(self, run_id: str) -> None:
        await asyncio.Event().wait()


@dataclass(frozen=True, slots=True)
class WaveResult:
    """一轮派发结果和事件意图，不直接写入事件存储。"""

    outcomes: tuple[TaskOutcome, ...]
    event_intents: tuple[dict[str, object], ...] = ()
    dispatched_task_ids: tuple[str, ...] = ()
    cancelled: bool = False


def _maybe_await(value: object) -> object:
    return value


async def _await_if_needed(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


def _task_id(node: object) -> str:
    if isinstance(node, dict):
        value = node.get("task_id")
    else:
        value = getattr(node, "task_id", None)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("TASK_INVALID:task_id")
    return value


def _node_dependencies(node: object) -> tuple[str, ...]:
    value = (
        node.get("depends_on", ())
        if isinstance(node, dict)
        else getattr(node, "depends_on", ())
    )
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _as_json_value(value: object) -> JsonValue:
    if isinstance(value, JsonObject):
        return value
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, list):
        return tuple(_as_json_value(item) for item in value)
    if isinstance(value, dict):
        entries: list[tuple[str, JsonValue]] = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("输出对象键必须是字符串")
            entries.append((key, _as_json_value(item)))
        return JsonObject(tuple(entries))
    raise TypeError("输出必须是 JSON 基础值")


def _as_json_object(value: object) -> JsonObject:
    if isinstance(value, JsonObject):
        return value
    converted = _as_json_value(value)
    if isinstance(converted, JsonObject):
        return converted
    return JsonObject()


def _failed_result_code(output: object) -> str:
    """把研究失败统一收敛为在线研究不可用，避免暴露 Specialist 内部码。"""
    if isinstance(output, JsonObject):
        code = dict(output.items).get("error_code")
        if isinstance(code, str) and code.startswith(("RESEARCH_", "EVIDENCE_")):
            return "RESEARCH_UNAVAILABLE"
    return "SPECIALIST_FAILED"


def _timeout_error_code(node: object) -> str:
    """研究节点超时统一映射为用户级研究不可用，其他节点保留通用超时。"""
    return (
        "RESEARCH_UNAVAILABLE"
        if getattr(node, "task_type", None) == "operation.research"
        else "TIMED_OUT"
    )


def _agent_id(candidate: object, node: object) -> str:
    if isinstance(candidate, str):
        return candidate
    if isinstance(candidate, SelectedSpecialist):
        return candidate.agent_id
    value = getattr(candidate, "agent_id", None)
    if isinstance(value, str):
        return value
    value = getattr(getattr(candidate, "spec", None), "agent_id", None)
    if isinstance(value, str):
        return value
    return _task_id(node)


def _full_usage(task: SupervisorTask | object) -> BudgetUsage:
    budget = getattr(task, "budget", None)
    if budget is None:
        return BudgetUsage(iterations=1)
    return BudgetUsage(
        iterations=budget.max_iterations,
        tool_calls=budget.max_tool_calls,
        input_tokens=budget.max_input_tokens,
        output_tokens=budget.max_output_tokens,
        elapsed_ms=budget.timeout_ms,
        cost_microunits=budget.max_cost_microunits,
    )


def _usage_from(value: object, fallback: BudgetUsage) -> BudgetUsage:
    if isinstance(value, BudgetUsage):
        return value
    if isinstance(value, JsonObject):
        raw = dict(value.items)
        fields = (
            "iterations",
            "tool_calls",
            "input_tokens",
            "output_tokens",
            "elapsed_ms",
            "cost_microunits",
        )
        if all(
            isinstance(raw.get(field), int) and not isinstance(raw.get(field), bool)
            for field in fields
        ):
            try:
                return BudgetUsage(*(cast(int, raw[field]) for field in fields))
            except (TypeError, ValueError):
                return fallback
    return fallback


class BoundedScheduler:
    """按最多四个任务一波执行，并隔离单个 Specialist 失败。"""

    def __init__(
        self,
        selector: _SelectorPort | SpecialistSelector,
        factory: _FactoryPort,
        dispatch_builder: DispatchBuilder | object,
        ledger: BudgetLedger | object | None = None,
        cancellation: object | None = None,
        *,
        clock: object | None = None,
        max_parallel_tasks: int = 4,
        graph: object | None = None,
        diagnostic_recorder: DiagnosticRecorderPort | None = None,
    ) -> None:
        if not hasattr(selector, "rank") or not hasattr(factory, "create"):
            raise TypeError("selector和factory必须提供必要端口")
        if not hasattr(dispatch_builder, "build"):
            raise TypeError("dispatch_builder必须提供build端口")
        if (
            cancellation is None
            and ledger is not None
            and hasattr(ledger, "wait_requested")
        ):
            cancellation, ledger = ledger, None
        if cancellation is None:
            cancellation = _NeverCancellationSignal()
        if (
            not isinstance(max_parallel_tasks, int)
            or isinstance(max_parallel_tasks, bool)
            or not 1 <= max_parallel_tasks <= 4
        ):
            raise ValueError("max_parallel_tasks必须在1到4之间")
        self._selector: _SelectorPort = cast(_SelectorPort, selector)
        self._factory = factory
        self._dispatch_builder = dispatch_builder
        self._ledger: _LedgerPort | None = cast(_LedgerPort | None, ledger)
        self._cancellation = cancellation
        self._clock = clock
        self._max_parallel = max_parallel_tasks
        self._graph = graph
        self._diagnostic_recorder = diagnostic_recorder or NoopDiagnosticRecorder()

    def _record_specialist_failure(
        self,
        *,
        task_id: str,
        agent_id: str | None,
        error_code: str,
        error_type: str,
        attempt: int,
        error_location: str | None = None,
    ) -> None:
        """记录 Specialist 边界失败，不写入请求正文或异常正文。"""

        try:
            self._diagnostic_recorder.record(
                DiagnosticRecord(
                    event_name="specialist_execution_failed",
                    component="scheduler",
                    level=DiagnosticLevel.ERROR,
                    capability="operation.specialist",
                    status="failed",
                    stage="specialist.run",
                    provider=agent_id,
                    reason_code=task_id,
                    error_code=error_code,
                    error_type=error_type,
                    error_location=error_location,
                    retryable=error_code == "TIMED_OUT",
                    attempt=attempt,
                )
            )
        except Exception:  # noqa: BLE001, 诊断不得改变调度结果
            return

    async def _cancel_requested(self, run_id: str) -> bool:
        checker = getattr(self._cancellation, "is_requested", None)
        if checker is None:
            return False
        return bool(await _await_if_needed(checker(run_id)))

    def _now_ms(self) -> int:
        if self._clock is not None:
            value = (
                self._clock()
                if callable(self._clock)
                else cast(_ClockPort, self._clock).now_epoch_ms()
            )
            return int(value)
        return int(time.time() * 1000)

    def _nodes(self, state: OperationSupervisorState) -> tuple[object, ...]:
        graph = self._graph
        if graph is not None and hasattr(graph, "tasks"):
            return tuple(cast(_GraphPort, graph).tasks)
        raw = state.get("task_graph")
        if isinstance(raw, dict):
            tasks = raw.get("tasks")
            if isinstance(tasks, list):
                return tuple(tasks)
        return tuple(
            SimpleNamespace(task_id=task_id, depends_on=())
            for task_id in state["task_statuses"]
        )

    def _ready_nodes(self, state: OperationSupervisorState) -> tuple[object, ...]:
        statuses = state["task_statuses"]
        nodes = {_task_id(node): node for node in self._nodes(state)}
        ready = [
            node
            for task_id, node in nodes.items()
            if statuses.get(task_id) == "ready"
            and all(
                statuses.get(dep) == "succeeded" for dep in _node_dependencies(node)
            )
        ]
        return tuple(sorted(ready, key=_task_id)[: self._max_parallel])

    async def _execute_node(
        self, state: OperationSupervisorState, node: object
    ) -> TaskOutcome:
        task_id = _task_id(node)
        candidates = tuple(self._selector.rank(node))
        parent_deadline = state["parent_deadline_epoch_ms"]
        if not candidates:
            return TaskOutcome(
                task_id,
                None,
                TaskExecutionStatus.FAILED,
                None,
                "SPECIALIST_UNAVAILABLE",
                (),
                (task_id,),
                BudgetUsage(),
                1,
                state["plan_revision"],
                state["fence_token"],
            )
        last_error = "SPECIALIST_FAILED"
        for candidate in candidates:
            agent_id = _agent_id(candidate, node)
            try:
                plugin = self._factory.create(agent_id)
                input_data = JsonObject()
                dispatch = self._dispatch_builder.build(
                    node,
                    candidate,
                    parent_run_id=state["run_id"],
                    parent_deadline_epoch_ms=parent_deadline,
                    input_data=input_data,
                    attempt=state["attempts"].get(task_id, 0) + 1,
                    revision=state["task_revisions"].get(task_id, 0),
                    fence_token=state["fence_token"],
                )
                run_method = getattr(plugin, "run", None) or getattr(
                    plugin, "execute", None
                )
                if run_method is None:
                    raise TypeError("Specialist缺少run端口")
                remaining_ms = max(0, parent_deadline - self._now_ms())
                child_budget = getattr(
                    getattr(dispatch, "task", dispatch), "budget", None
                )
                child_timeout = getattr(child_budget, "timeout_ms", remaining_ms)
                timeout_ms = min(remaining_ms, child_timeout)
                if timeout_ms <= 0:
                    raise TimeoutError("父任务截止时间已到")
                # S1 AgentPlugin 的公开契约只接收 SupervisorTask；TaskDispatch
                # 是 Supervisor 内部的预算与栅栏包装，不能泄漏给 Specialist。
                plugin_task = getattr(dispatch, "task", dispatch)
                run_task = asyncio.create_task(
                    _await_if_needed(run_method(plugin_task))
                )
                cancel_waiter = getattr(self._cancellation, "wait_requested", None)
                cancel_task = (
                    asyncio.create_task(
                        _await_if_needed(cancel_waiter(state["run_id"]))
                    )
                    if cancel_waiter is not None
                    else None
                )
                try:
                    wait_set = {run_task}
                    if cancel_task is not None:
                        wait_set.add(cancel_task)
                    try:
                        async with asyncio.timeout(timeout_ms / 1000):
                            done, _ = await asyncio.wait(
                                wait_set,
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                    except TimeoutError:
                        run_task.cancel()
                        await asyncio.gather(run_task, return_exceptions=True)
                        timeout_code = _timeout_error_code(node)
                        self._record_specialist_failure(
                            task_id=task_id,
                            agent_id=agent_id,
                            error_code=timeout_code,
                            error_type="TimeoutError",
                            attempt=state["attempts"].get(task_id, 0) + 1,
                        )
                        return TaskOutcome(
                            task_id,
                            agent_id,
                            TaskExecutionStatus.FAILED,
                            None,
                            timeout_code,
                            (),
                            (task_id,),
                            BudgetUsage(),
                            1,
                            state["plan_revision"],
                            state["fence_token"],
                        )
                    if cancel_task is not None and cancel_task in done:
                        run_task.cancel()
                        await asyncio.gather(run_task, return_exceptions=True)
                        return TaskOutcome(
                            task_id,
                            agent_id,
                            TaskExecutionStatus.CANCELLED,
                            None,
                            "CANCELLED",
                            (),
                            (task_id,),
                            BudgetUsage(),
                            1,
                            state["plan_revision"],
                            state["fence_token"],
                        )
                    raw = await run_task
                finally:
                    if cancel_task is not None and not cancel_task.done():
                        cancel_task.cancel()
                        await asyncio.gather(cancel_task, return_exceptions=True)
                usage = _full_usage(getattr(dispatch, "task", dispatch))
                output: object = raw
                if isinstance(raw, tuple) and len(raw) == 2:
                    output, usage = raw[0], _usage_from(raw[1], usage)
                elif isinstance(raw, RunResult):
                    status = (
                        TaskExecutionStatus.SUCCEEDED
                        if raw.status.value == "succeeded"
                        else TaskExecutionStatus.FAILED
                    )
                    output = raw.output
                    if status is TaskExecutionStatus.FAILED:
                        failure_code = _failed_result_code(output)
                        self._record_specialist_failure(
                            task_id=task_id,
                            agent_id=agent_id,
                            error_code=failure_code,
                            error_type="SpecialistRunResult",
                            attempt=state["attempts"].get(task_id, 0) + 1,
                        )
                        return TaskOutcome(
                            task_id,
                            agent_id,
                            status,
                            None,
                            failure_code,
                            (),
                            (task_id,),
                            usage,
                            1,
                            state["plan_revision"],
                            state["fence_token"],
                        )
                elif isinstance(raw, dict):
                    raw_status = raw.get("status")
                    raw_fence = raw.get("fence_token")
                    if isinstance(raw_fence, int) and raw_fence != state["fence_token"]:
                        return TaskOutcome(
                            task_id,
                            agent_id,
                            TaskExecutionStatus.FAILED,
                            None,
                            "LATE_RESULT_IGNORED",
                            (),
                            (task_id,),
                            BudgetUsage(),
                            1,
                            state["plan_revision"],
                            state["fence_token"],
                        )
                    if raw_status in {"failed", "cancelled", "timed_out"}:
                        last_error = "SPECIALIST_FAILED"
                        continue
                    output = {
                        key: value
                        for key, value in raw.items()
                        if key not in {"status", "usage"}
                    }
                result = _as_json_object(output)
                if self._ledger is not None:
                    cast(_LedgerPort, self._ledger).consume(task_id, usage)
                return TaskOutcome(
                    task_id,
                    agent_id,
                    TaskExecutionStatus.SUCCEEDED,
                    result,
                    None,
                    (task_id,),
                    (),
                    usage,
                    1,
                    state["plan_revision"],
                    state["fence_token"],
                )
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                timeout_code = _timeout_error_code(node)
                self._record_specialist_failure(
                    task_id=task_id,
                    agent_id=agent_id,
                    error_code=timeout_code,
                    error_type="TimeoutError",
                    attempt=state["attempts"].get(task_id, 0) + 1,
                )
                return TaskOutcome(
                    task_id,
                    agent_id,
                    TaskExecutionStatus.FAILED,
                    None,
                    timeout_code,
                    (),
                    (task_id,),
                    BudgetUsage(),
                    1,
                    state["plan_revision"],
                    state["fence_token"],
                )
            except Exception as error:  # noqa: BLE001  # 单个候选失败必须隔离并切换下一个候选
                self._record_specialist_failure(
                    task_id=task_id,
                    agent_id=agent_id,
                    error_code="SPECIALIST_FAILED",
                    error_type=type(error).__name__,
                    attempt=state["attempts"].get(task_id, 0) + 1,
                    error_location=safe_exception_location(error),
                )
                last_error = "SPECIALIST_FAILED"
                continue
        return TaskOutcome(
            task_id,
            None,
            TaskExecutionStatus.FAILED,
            None,
            last_error,
            (),
            (task_id,),
            BudgetUsage(),
            1,
            state["plan_revision"],
            state["fence_token"],
        )

    async def run_wave(self, state: OperationSupervisorState) -> WaveResult:
        """执行一轮最多四个 READY 任务，单个失败不取消同波任务。"""

        validate_supervisor_state(state)
        if await self._cancel_requested(state["run_id"]):
            return WaveResult((), (), (), True)
        nodes = self._ready_nodes(state)
        if not nodes:
            return WaveResult(())
        outcomes = tuple(
            await asyncio.gather(
                *(self._execute_node(state, node) for node in nodes),
                return_exceptions=False,
            )
        )
        intents: tuple[dict[str, object], ...] = tuple(
            {
                "task_id": outcome.task_id,
                "event_type": outcome.status.value,
                "error_code": outcome.error_code,
            }
            for outcome in outcomes
        )
        return WaveResult(
            outcomes,
            intents,
            tuple(outcome.task_id for outcome in outcomes),
            any(item.status is TaskExecutionStatus.CANCELLED for item in outcomes),
        )


__all__ = ["BoundedScheduler", "WaveResult"]
