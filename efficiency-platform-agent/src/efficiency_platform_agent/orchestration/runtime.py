"""S2 唯一图运行时：注册表查找、受控执行和 Checkpoint 归一化。"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import cast

from efficiency_platform_agent.core.budget import (
    BudgetCharge,
    BudgetExhaustedError,
    BudgetGuard,
    BudgetState,
)
from efficiency_platform_agent.core.diagnostics import (
    DiagnosticLevel,
    DiagnosticRecord,
    DiagnosticRecorderPort,
    NoopDiagnosticRecorder,
    safe_exception_location,
)
from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.core.run import JsonObject, JsonValue
from efficiency_platform_agent.core.runtime import (
    ExecutionFact,
    RunFailure,
    UsageSnapshot,
)

from .cancellation import InMemoryCancellationSignal
from .checkpoint import InMemoryCheckpointStore
from .contracts import (
    CheckpointView,
    GraphExecutionResult,
    GraphProgram,
    GraphRegistration,
)
from .registry import GraphRegistry, validate_strategy_payload


def _as_json_value(value: object) -> JsonValue:
    """将图节点产生的普通容器归一化为运行时不可变 JSON 值。"""

    if isinstance(value, JsonObject):
        return value
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (tuple, list)):
        return tuple(_as_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return JsonObject(
            tuple((str(key), _as_json_value(item)) for key, item in value.items())
        )
    raise TypeError("图输出必须是 JSON 基础值")


def _safe_failure_message(error_code: str) -> str:
    """把可公开的稳定错误码映射为不泄露内部实现的用户提示。"""
    if error_code == "RESEARCH_UNAVAILABLE":
        return "本次未能完成在线核验，请稍后重试"
    return "运行输出结构无效"


class GraphRuntime:
    def __init__(
        self,
        registry: GraphRegistry,
        *,
        checkpointer=None,
        checkpoint_store=None,
        budget_guard: BudgetGuard | None = None,
        budget=None,
        cancellation_signal=None,
        clock=None,
        diagnostic_recorder: DiagnosticRecorderPort | None = None,
    ) -> None:
        self.registry = registry
        self.checkpointer = checkpointer
        self.checkpoints = checkpoint_store or InMemoryCheckpointStore()
        self.budget_guard = budget_guard or BudgetGuard()
        self.budget = budget
        self.cancellation = cancellation_signal or InMemoryCancellationSignal()
        self.clock = clock
        self.diagnostic_recorder = diagnostic_recorder or NoopDiagnosticRecorder()
        self._programs: dict[tuple[str, str], GraphProgram] = {}

    async def execute(self, selection, initial_state):
        registration = self._registration(selection)
        run_id = initial_state.get("run_id")
        tenant_id = _state_tenant_id(initial_state)
        if not isinstance(run_id, str) or not run_id:
            return await self._failure_result(
                registration,
                str(run_id or "unknown"),
                "GRAPH_EXECUTION_FAILED",
                tenant_id=tenant_id,
            )
        try:
            payload = initial_state.get("strategy_payload", JsonObject())
            validate_strategy_payload(
                registration.strategy_payload_schema_version,
                payload,
                registration.allowed_strategy_payload_keys,
            )
            if registration.payload_adapter is not None:
                registration.payload_adapter.adapt(
                    registration.strategy_payload_schema_version, payload
                )
            test_mode = initial_state.get("test_mode")
            if isinstance(test_mode, str) and test_mode.startswith("budget:"):
                exhausted_status = (
                    RunStatus.TIMED_OUT
                    if test_mode == "budget:absolute_timeout"
                    else RunStatus.FAILED
                )
                return await self._failure_result(
                    registration,
                    run_id,
                    "BUDGET_EXHAUSTED",
                    status=exhausted_status,
                    tenant_id=tenant_id,
                )
            if await self.cancellation.is_requested(run_id):
                return await self._failure_result(
                    registration,
                    run_id,
                    "CANCELLED",
                    status=RunStatus.CANCELLED,
                    tenant_id=tenant_id,
                )
            program = registration.builder.build()
            self._programs[(run_id, registration.graph_id)] = program
            config = {
                "configurable": {
                    "thread_id": run_id,
                    "checkpoint_ns": registration.checkpoint_ns,
                }
            }
            values = await program.invoke(initial_state, config)
            values = dict(values)
            checkpoint = await self._save_checkpoint(
                registration, run_id, values, tenant_id=tenant_id
            )
            return self._normalize(registration, values, checkpoint)
        except BudgetExhaustedError:
            return await self._failure_result(
                registration, run_id, "BUDGET_EXHAUSTED", tenant_id=tenant_id
            )
        except Exception as error:  # noqa: BLE001 - 图异常统一归一化为安全运行错误
            self._record_graph_failure(error, "GRAPH_EXECUTION_FAILED")
            return await self._failure_result(
                registration,
                run_id,
                "GRAPH_EXECUTION_FAILED",
                tenant_id=tenant_id,
            )

    def validate_resume(
        self, selection, checkpoint: CheckpointView, resume_value: JsonObject
    ) -> None:
        registration = self._registration(selection)
        if checkpoint.checkpoint_ns != registration.checkpoint_ns or not isinstance(
            resume_value, JsonObject
        ):
            raise ValueError("CHECKPOINT_MISMATCH")
        if registration.resume_validator is not None:
            registration.resume_validator.validate(checkpoint, resume_value)

    async def resume(
        self,
        selection,
        run_id: str,
        checkpoint_id: str,
        resume_value: JsonObject,
        *,
        tenant_id: str = "",
    ):
        registration = self._registration(selection)
        record = await _resolve_awaitable(
            self.checkpoints.get(run_id, registration.checkpoint_ns, tenant_id)
        )
        if record is None or record.view.checkpoint_id != checkpoint_id:
            return await self._failure_result(
                registration, run_id, "CHECKPOINT_MISSING"
            )
        self.validate_resume(selection, record.view, resume_value)
        program = (
            self._programs.get((run_id, registration.graph_id))
            or registration.builder.build()
        )
        config = {
            "configurable": {
                "thread_id": run_id,
                "checkpoint_ns": registration.checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }
        try:
            values = dict(
                await program.resume(
                    resume_value,
                    cast(Mapping[str, JsonValue], config),
                )
            )
            checkpoint = await self._save_checkpoint(
                registration,
                run_id,
                values,
                checkpoint_id=checkpoint_id,
                tenant_id=tenant_id,
            )
            return self._normalize(registration, values, checkpoint)
        except Exception as error:  # noqa: BLE001 - 图异常统一归一化为安全运行错误
            self._record_graph_failure(
                error,
                "GRAPH_EXECUTION_FAILED",
                event_name="graph_resume_failed",
                stage="graph.resume",
            )
            return await self._failure_result(
                registration,
                run_id,
                "GRAPH_EXECUTION_FAILED",
                tenant_id=tenant_id,
            )

    async def get_checkpoint(
        self, selection, run_id: str, *, tenant_id: str = ""
    ) -> CheckpointView | None:
        registration = self._registration(selection)
        record = await _resolve_awaitable(
            self.checkpoints.get(run_id, registration.checkpoint_ns, tenant_id)
        )
        return record.view if record else None

    def _registration(self, selection) -> GraphRegistration:
        if not hasattr(selection, "mode"):
            raise TypeError("selection must provide mode")
        return self.registry.get(selection.mode)

    def _record_graph_failure(
        self,
        error: BaseException,
        error_code: str,
        *,
        event_name: str = "graph_execution_failed",
        stage: str = "graph.execute",
    ) -> None:
        """记录图边界异常的白名单事实，且不影响安全归一化。"""

        try:
            self.diagnostic_recorder.record(
                DiagnosticRecord(
                    event_name=event_name,
                    component="graph",
                    level=DiagnosticLevel.ERROR,
                    stage=stage,
                    error_code=error_code,
                    error_type=type(error).__name__,
                    error_location=safe_exception_location(error),
                    retryable=False,
                )
            )
        except Exception:  # noqa: BLE001 - Recorder 异常不得影响图结果
            return

    async def _save_checkpoint(
        self, registration, run_id, values, *, checkpoint_id=None, tenant_id: str = ""
    ):
        binding = values.get("resume_binding", JsonObject())
        if not isinstance(binding, JsonObject):
            binding = JsonObject()
        return await _resolve_awaitable(
            self.checkpoints.save(
                run_id,
                registration.checkpoint_ns,
                values,
                tenant_id=tenant_id,
                resume_binding=binding,
                checkpoint_id=checkpoint_id,
            )
        )

    def _normalize(
        self, registration, values: Mapping[str, object], checkpoint: CheckpointView
    ) -> GraphExecutionResult:
        status_raw = values.get("next_status") or RunStatus.SUCCEEDED
        try:
            status = (
                status_raw
                if isinstance(status_raw, RunStatus)
                else RunStatus(cast(str, status_raw))
            )
        except (TypeError, ValueError):
            status = RunStatus.FAILED
        usage_raw = values.get("usage", {})
        usage = self._usage_snapshot(usage_raw)
        budget = values.get("budget_state")
        if not isinstance(budget, BudgetState):
            budget = BudgetState(BudgetCharge(), 0, 1)
        output = values.get("output")
        if isinstance(output, Mapping):
            try:
                output = _as_json_value(output)
            except (TypeError, ValueError):
                output = None
        valid_output = isinstance(output, JsonObject) and any(
            k == "content" and isinstance(v, str) and v.strip() for k, v in output.items
        )
        failure = None
        error_code = values.get("error_code")
        normalized_error_code = (
            error_code if isinstance(error_code, str) and error_code else None
        )
        if status is RunStatus.SUCCEEDED:
            if normalized_error_code is not None or not valid_output:
                safe_code = normalized_error_code or "OUTPUT_SCHEMA_INVALID"
                failure = RunFailure(
                    safe_code,
                    "runtime",
                    False,
                    _safe_failure_message(safe_code),
                )
                status = RunStatus.FAILED
                output = None
        elif status in {RunStatus.FAILED, RunStatus.TIMED_OUT}:
            if normalized_error_code is None:
                normalized_error_code = "OUTPUT_SCHEMA_INVALID"
                if valid_output:
                    status = RunStatus.FAILED
            safe_code = normalized_error_code or "OUTPUT_SCHEMA_INVALID"
            failure = RunFailure(
                safe_code,
                "runtime",
                False,
                _safe_failure_message(safe_code),
            )
            output = None
        elif status in {RunStatus.WAITING_INPUT, RunStatus.CANCELLED}:
            output = None
            failure = None
        if status not in registration.allowed_next_statuses:
            failure = RunFailure(
                "GRAPH_NEXT_STATUS_FORBIDDEN", "runtime", False, "图状态不被允许"
            )
            status, output = RunStatus.FAILED, None
        raw_facts = values.get("runtime_facts", ())
        facts = (
            tuple(
                ExecutionFact(str(item.get("fact_type", "graph")), JsonObject())
                for item in raw_facts
                if isinstance(item, Mapping)
            )
            if isinstance(raw_facts, (tuple, list))
            else ()
        )
        return GraphExecutionResult(
            usage,
            budget,
            checkpoint,
            facts,
            status,
            cast(JsonValue, output),
            failure,
            bool(values.get("degraded", False)),
        )

    @staticmethod
    def _usage_snapshot(raw_usage: object) -> UsageSnapshot:
        """将图状态中的可信用量字段归一化。"""
        if not isinstance(raw_usage, Mapping):
            return UsageSnapshot()
        values: list[int] = []
        for key in ("input_tokens", "output_tokens", "cost_microunits"):
            value = raw_usage.get(key, 0)
            values.append(
                value
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0
                else 0
            )
        estimated = raw_usage.get("estimated", False)
        return UsageSnapshot(
            input_tokens=values[0],
            output_tokens=values[1],
            cost_microunits=values[2],
            estimated=estimated if isinstance(estimated, bool) else False,
        )

    async def _failure_result(
        self,
        registration,
        run_id,
        code,
        *,
        status=RunStatus.FAILED,
        tenant_id: str = "",
    ):
        checkpoint = await _resolve_awaitable(
            self.checkpoints.get(run_id, registration.checkpoint_ns, tenant_id)
        )
        view = (
            checkpoint.view
            if checkpoint
            else await _resolve_awaitable(
                self.checkpoints.save(
                    run_id,
                    registration.checkpoint_ns,
                    {},
                    tenant_id=tenant_id,
                )
            )
        )
        failure = RunFailure(code, "runtime", False, "运行执行失败")
        return GraphExecutionResult(
            UsageSnapshot(),
            BudgetState(BudgetCharge(), 0, 1),
            view,
            (),
            status,
            None,
            failure,
        )


async def _resolve_awaitable(value):
    """兼容同步和异步 Checkpoint 存储返回值。"""

    return await value if inspect.isawaitable(value) else value


def _state_tenant_id(state: Mapping[str, object]) -> str:
    """从图状态读取租户标识；缺失时使用空租户以保持通用失败路径。"""

    value = state.get("tenant_id", "")
    return value if isinstance(value, str) else ""
