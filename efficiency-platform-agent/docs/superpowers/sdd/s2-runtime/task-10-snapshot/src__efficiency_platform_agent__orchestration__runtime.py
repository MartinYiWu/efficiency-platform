"""S2 唯一图运行时：注册表查找、受控执行和 Checkpoint 归一化。"""
from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from efficiency_platform_agent.core.budget import (
    BudgetCharge,
    BudgetExhaustedError,
    BudgetGuard,
    BudgetState,
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


class GraphRuntime:
    def __init__(self, registry: GraphRegistry, *, checkpointer=None, checkpoint_store=None, budget_guard: BudgetGuard | None = None, budget=None, cancellation_signal=None, clock=None) -> None:
        self.registry = registry
        self.checkpointer = checkpointer
        self.checkpoints = checkpoint_store or InMemoryCheckpointStore()
        self.budget_guard = budget_guard or BudgetGuard()
        self.budget = budget
        self.cancellation = cancellation_signal or InMemoryCancellationSignal()
        self.clock = clock
        self._programs: dict[tuple[str, str], GraphProgram] = {}

    async def execute(self, selection, initial_state):
        registration = self._registration(selection)
        run_id = initial_state.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            return self._failure_result(registration, str(run_id or "unknown"), "GRAPH_EXECUTION_FAILED")
        try:
            payload = initial_state.get("strategy_payload", JsonObject())
            validate_strategy_payload(registration.strategy_payload_schema_version, payload, registration.allowed_strategy_payload_keys)
            if registration.payload_adapter is not None:
                registration.payload_adapter.adapt(registration.strategy_payload_schema_version, payload)
            if await self.cancellation.is_requested(run_id):
                return self._failure_result(registration, run_id, "CANCELLED", status=RunStatus.CANCELLED)
            program = registration.builder.build()
            self._programs[(run_id, registration.graph_id)] = program
            config = {"configurable": {"thread_id": run_id, "checkpoint_ns": registration.checkpoint_ns}}
            values = await program.invoke(initial_state, config)
            values = dict(values)
            checkpoint = await self._save_checkpoint(registration, run_id, values)
            return self._normalize(registration, values, checkpoint)
        except BudgetExhaustedError:
            return self._failure_result(registration, run_id, "BUDGET_EXHAUSTED")
        except Exception:  # noqa: BLE001 - 图异常统一归一化为安全运行错误
            return self._failure_result(registration, run_id, "GRAPH_EXECUTION_FAILED")

    def validate_resume(self, selection, checkpoint: CheckpointView, resume_value: JsonObject) -> None:
        registration = self._registration(selection)
        if checkpoint.checkpoint_ns != registration.checkpoint_ns or not isinstance(resume_value, JsonObject):
            raise ValueError("CHECKPOINT_MISMATCH")
        if registration.resume_validator is not None:
            registration.resume_validator.validate(checkpoint, resume_value)

    async def resume(self, selection, run_id: str, checkpoint_id: str, resume_value: JsonObject):
        registration = self._registration(selection)
        record = self.checkpoints.get(run_id, registration.checkpoint_ns)
        if record is None or record.view.checkpoint_id != checkpoint_id:
            return self._failure_result(registration, run_id, "CHECKPOINT_MISSING")
        self.validate_resume(selection, record.view, resume_value)
        program = self._programs.get((run_id, registration.graph_id)) or registration.builder.build()
        config = {"configurable": {"thread_id": run_id, "checkpoint_ns": registration.checkpoint_ns, "checkpoint_id": checkpoint_id}}
        try:
            values = dict(
                await program.resume(
                    resume_value,
                    cast(Mapping[str, JsonValue], config),
                )
            )
            checkpoint = await self._save_checkpoint(registration, run_id, values, checkpoint_id=checkpoint_id)
            return self._normalize(registration, values, checkpoint)
        except Exception:  # noqa: BLE001 - 图异常统一归一化为安全运行错误
            return self._failure_result(registration, run_id, "GRAPH_EXECUTION_FAILED")

    async def get_checkpoint(self, selection, run_id: str) -> CheckpointView | None:
        registration = self._registration(selection)
        record = self.checkpoints.get(run_id, registration.checkpoint_ns)
        return record.view if record else None

    def _registration(self, selection) -> GraphRegistration:
        if not hasattr(selection, "mode"):
            raise TypeError("selection must provide mode")
        return self.registry.get(selection.mode)

    async def _save_checkpoint(self, registration, run_id, values, *, checkpoint_id=None):
        binding = values.get("resume_binding", JsonObject())
        if not isinstance(binding, JsonObject): binding = JsonObject()
        return self.checkpoints.save(run_id, registration.checkpoint_ns, values, resume_binding=binding, checkpoint_id=checkpoint_id)

    def _normalize(self, registration, values: Mapping[str, object], checkpoint: CheckpointView) -> GraphExecutionResult:
        status_raw = values.get("next_status", RunStatus.SUCCEEDED)
        try: status = status_raw if isinstance(status_raw, RunStatus) else RunStatus(cast(str, status_raw))
        except (TypeError, ValueError): status = RunStatus.FAILED
        usage_raw = values.get("usage", {})
        usage = self._usage_snapshot(usage_raw)
        budget = values.get("budget_state")
        if not isinstance(budget, BudgetState): budget = BudgetState(BudgetCharge(), 0, 1)
        output = values.get("output")
        valid_output = isinstance(output, JsonObject) and any(k == "content" and isinstance(v, str) and v.strip() for k, v in output.items)
        failure = None
        error_code = values.get("error_code")
        if status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.TIMED_OUT} and (error_code or not valid_output):
            safe_code = error_code if isinstance(error_code, str) and error_code else "OUTPUT_SCHEMA_INVALID"
            failure = RunFailure(safe_code, "runtime", False, "运行输出结构无效")
            status = RunStatus.FAILED
            output = None
        elif status in {RunStatus.WAITING_INPUT, RunStatus.CANCELLED}:
            output = None
            failure = None
        if status not in registration.allowed_next_statuses:
            failure = RunFailure("GRAPH_NEXT_STATUS_FORBIDDEN", "runtime", False, "图状态不被允许")
            status, output = RunStatus.FAILED, None
        raw_facts = values.get("runtime_facts", ())
        facts = tuple(
            ExecutionFact(str(item.get("fact_type", "graph")), JsonObject())
            for item in raw_facts
            if isinstance(item, Mapping)
        ) if isinstance(raw_facts, (tuple, list)) else ()
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
            values.append(value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0)
        estimated = raw_usage.get("estimated", False)
        return UsageSnapshot(
            input_tokens=values[0],
            output_tokens=values[1],
            cost_microunits=values[2],
            estimated=estimated if isinstance(estimated, bool) else False,
        )

    def _failure_result(self, registration, run_id, code, *, status=RunStatus.FAILED):
        checkpoint = self.checkpoints.get(run_id, registration.checkpoint_ns)
        view = checkpoint.view if checkpoint else self.checkpoints.save(run_id, registration.checkpoint_ns, {})
        failure = RunFailure(code, "runtime", False, "运行执行失败")
        return GraphExecutionResult(UsageSnapshot(), BudgetState(BudgetCharge(), 0, 1), view, (), status, None, failure)
