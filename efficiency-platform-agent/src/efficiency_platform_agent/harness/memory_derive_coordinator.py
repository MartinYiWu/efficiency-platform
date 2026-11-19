"""原运行内摘要模板协调：登记真实基线、通知与有界等待，不生成或提交摘要。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol, cast
from weakref import ReferenceType, ref

from pydantic import ValidationError

from efficiency_platform_agent.capabilities.model.memory_derive_handler import (
    MemoryDeriveHandler,
    OriginalDeriveFrame,
)
from efficiency_platform_agent.context.compaction import CompactionBaseline
from efficiency_platform_agent.contracts.memory_derive import (
    DeriveAssetRefs,
    MemoryDeriveRequest,
)
from efficiency_platform_agent.contracts.memory_derive_template import (
    MemoryDeriveTemplate,
)
from efficiency_platform_agent.core.context_ports import (
    ContextMetadata,
    ContextOperation,
)
from efficiency_platform_agent.core.execution_control import (
    RunControl,
    current_run_control,
)
from efficiency_platform_agent.core.memory import ExecutionScope
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionRecord,
    MemoryExecutionStore,
)
from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.core.run_context_binding import current_run_context
from efficiency_platform_agent.harness.memory_derive_runtime import (
    FrozenOriginalDeriveSourceChecker,
    LiveOriginalDeriveFrames,
)
from efficiency_platform_agent.memory.summary_policy import SummaryPolicy
from efficiency_platform_agent.memory.summary_validation import SummaryTaskState
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)


class CoordinatorLedger(Protocol):
    def active_budget_id(self) -> str | None: ...
    def snapshot(self, budget_id: str | None = None) -> dict[str, object]: ...
    def bind_execution(
        self,
        tenant_id: str,
        run_id: str,
        duration_ms: int,
        maximum_attempts: int = 3,
        *,
        context_scope=None,
    ) -> int: ...
    def check_execution(self, tenant_id: str, run_id: str) -> None: ...


@dataclass(slots=True)
class _RunTemplate:
    record: MemoryExecutionRecord | None = field(repr=False)
    template: MemoryDeriveTemplate | None = field(repr=False)
    budget_id: str
    deadline: int
    active: bool = True


@dataclass(slots=True)
class _Wait:
    scope: ExecutionScope
    runtime_id: str
    original_operation_id: str
    plan_id: str
    fingerprint: str
    control: ReferenceType[RunControl]
    task: ReferenceType[asyncio.Task[Any]]
    event: asyncio.Event = field(default_factory=asyncio.Event)
    notified: bool = False
    finished: bool = False


class MemoryDeriveCoordinator:
    def __init__(
        self,
        frames: LiveOriginalDeriveFrames,
        handler: MemoryDeriveHandler,
        ledger: CoordinatorLedger,
        derive_metadata: ContextMetadata,
        execution_store: MemoryExecutionStore,
        notify_waitasync: Callable[[str, dict[str, str]], Awaitable[None]],
    ):
        self.frames, self.handler, self.ledger = frames, handler, ledger
        self.metadata, self.execution_store, self.notify = (
            derive_metadata,
            execution_store,
            notify_waitasync,
        )
        self._waits: dict[tuple[str, str], _Wait] = {}
        self._counter = ConservativeRequestTokenCounter()

    def _budget(self, expected: str | None = None) -> tuple[str, int] | None:
        budget_id = self.ledger.active_budget_id()
        if budget_id is None or (expected is not None and budget_id != expected):
            return None
        snapshot = self.ledger.snapshot(budget_id)
        if (
            snapshot.get("budget_id") != budget_id
            or snapshot.get("stopped")
            or cast(int, snapshot.get("remaining_calls", 0)) < 1
            or cast(int, snapshot.get("deadline_epoch_ms", 0))
            <= int(time.time() * 1000)
        ):
            return None
        prices = cast(list[dict[str, Any]], snapshot.get("prices", []))
        price = next(
            (
                item
                for item in prices
                if (item.get("provider"), item.get("model"))
                == (self.metadata.capacity.provider, self.metadata.capacity.model)
            ),
            None,
        )
        if (
            price is None
            or not price.get("pricing_version")
            or not price.get("pricing_source")
            or price.get("input_microunits_per_million", 0) <= 0
            or price.get("output_microunits_per_million", 0) <= 0
            or price.get("max_cost_microunits_per_attempt", 0) <= 0
            or price.get("max_input_tokens", 0) <= 0
            or price.get("max_output_tokens", 0)
            < self.metadata.limits.output_reserve_tokens
            or cast(int, snapshot.get("remaining_cost_microunits", 0))
            < price["max_cost_microunits_per_attempt"]
        ):
            return None
        return budget_id, cast(int, snapshot["deadline_epoch_ms"]) // 1000

    @contextmanager
    def for_run(self, record: MemoryExecutionRecord) -> Iterator[None]:
        binding, control, task = (
            current_run_context(),
            current_run_control(),
            asyncio.current_task(),
        )
        if (
            binding is None
            or control is None
            or task is None
            or (
                record.context != binding.memory_context
                or record.state != "ACTIVE"
                or record.deadline_epoch_seconds != binding.deadline_epoch_seconds
            )
        ):
            raise ValueError("DERIVE_ORIGINAL_EXECUTION_REQUIRED")
        control.check()
        state = None
        try:
            raw = getattr(record.context, "derive_template_json", None)
            if (
                not self.handler.enabled
                or record.context.policy.max_paid_operations != 1
                or raw is None
                or len(raw.encode("utf-8")) > 1048576
            ):
                raise ValueError("DERIVE_TEMPLATE_DISABLED")
            template = MemoryDeriveTemplate.model_validate_json(raw)
            expected_assets = (
                ("derive-prompt/2", "derive-schema/2")
                if template.mode == "SUMMARY"
                else ("derive-prompt/3", "derive-schema/3")
            )
            if (
                self.metadata.prompt_version,
                self.metadata.output_schema_version,
            ) != expected_assets:
                raise ValueError("DERIVE_PUBLISHED_ASSET_MISMATCH")
            scope = template.scope.to_core()
            if (
                (scope.conversation, template.task_id, template.execution_id)
                != (binding.conversation, binding.task_id, binding.execution_id)
                or template.deadline_epoch_seconds > binding.deadline_epoch_seconds
                or template.deadline_epoch_seconds <= time.time()
                or not set(self._dependencies(template)).issubset(
                    record.context.packet.safety_dependencies
                )
                or not self.metadata.capacity.verified
                or self.metadata.node_id != "memory.derive"
                or not any(
                    (grant.node_id, grant.execution_agent_id, grant.purpose)
                    == (scope.subtask_id, scope.execution_agent_id, scope.purpose)
                    for grant in record.context.execution_grants
                )
            ):
                raise ValueError("DERIVE_TEMPLATE_BINDING_CONFLICT")
            budget = self._budget()
            if budget is None:
                raise ValueError("DERIVE_BUDGET_UNAVAILABLE")
            budget_id, budget_deadline = budget
            deadline = min(
                template.deadline_epoch_seconds,
                record.deadline_epoch_seconds,
                budget_deadline,
            )
            duration_ms = min(600000, int(deadline * 1000 - time.time() * 1000))
            if duration_ms <= 0:
                raise ValueError("DERIVE_DEADLINE_EXCEEDED")
            persisted = self.ledger.bind_execution(
                binding.conversation.tenant_id,
                record.runtime_id,
                duration_ms,
                context_scope=binding.conversation,
            )
            state = _RunTemplate(
                record, template, budget_id, min(deadline, persisted // 1000)
            )
            del raw, template
        except (ValidationError, PaidBudgetError, ValueError, TypeError):
            state = None
        if state is None:
            yield
            return
        try:
            with self.frames.authorized_scope(
                lambda baseline, operation: self._frame(state, baseline, operation)
            ):
                yield
        finally:
            state.active = False
            state.record = None
            state.template = None
            key = (binding.conversation.tenant_id, binding.execution_id)
            waiting = self._waits.get(key)
            if waiting is not None and waiting.runtime_id == record.runtime_id:
                self._waits.pop(key, None)
                waiting.event.set()

    @staticmethod
    def _dependencies(template: MemoryDeriveTemplate):
        return tuple(
            dict.fromkeys(
                dependency.to_core()
                for source in template.sources
                for dependency in source.metadata.source_dependencies
            )
        )

    def _frame(
        self,
        state: _RunTemplate,
        baseline: CompactionBaseline,
        operation: ContextOperation,
    ) -> tuple[OriginalDeriveFrame, MemoryDeriveRequest] | None:
        template, record = state.template, state.record
        binding, control, task = (
            current_run_context(),
            current_run_control(),
            asyncio.current_task(),
        )
        if (
            not state.active
            or template is None
            or record is None
            or binding is None
            or control is None
            or task is None
        ):
            return None
        scope = baseline.window_policy.scope
        key = (scope.conversation.tenant_id, scope.execution_id)
        cap, total = (
            baseline.limits.input_cap(),
            baseline.view.measurement.total_upper_bound,
        )
        if (
            scope != template.scope.to_core()
            or scope.purpose != "assistant_response"
            or binding.memory_context != record.context
            or cap <= 0
            or (
                total * 100 < cap * 70
                and getattr(baseline.window_policy, "need_summary", False) is not True
            )
            or key in self._waits
            or time.time() >= state.deadline
        ):
            return None
        try:
            if self._budget(state.budget_id) is None:
                return None
            self.ledger.check_execution(scope.conversation.tenant_id, record.runtime_id)
            SummaryPolicy().admit(
                template.mode,
                tuple(source.metadata for source in template.sources),
                template.scope.conversation,
                now=int(time.time()),
            )
            if not set(self._dependencies(template)).issubset(
                baseline.window_policy.authorized_dependencies
            ):
                return None
        except (PaidBudgetError, ValueError):
            return None
        assets = DeriveAssetRefs(
            memory_policy_version=record.context.policy.version,
            window_policy_version=baseline.window_policy_version,
            model_ref=self.metadata.capacity.model_version,
            prompt_ref=self.metadata.prompt_version,
            schema_ref=self.metadata.output_schema_version,
        )
        canonical = json.dumps(
            {
                "request": asdict(baseline.view.request),
                "assets": assets.model_dump(mode="json"),
                "window_policy": baseline.window_policy_version,
                "model": asdict(baseline.capacity),
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = MemoryDeriveRequest(
            contract_version="memory-derive/1",
            plan_id=template.plan_id,
            plan_fingerprint="0" * 64,
            runtime_id=record.runtime_id,
            runtime_kind=cast(
                Literal["OPERATIONS", "CUSTOMER_SERVICE"], record.runtime_kind
            ),
            run_id=record.runtime_id,
            operation_id=template.operation_id,
            authorization_ref=record.context.packet.parent_authorization_ref,
            budget_id=state.budget_id,
            deadline_epoch_seconds=state.deadline,
            execution_scope=template.scope,
            mode=template.mode,
            baseline_ref="baseline-" + hashlib.sha256(canonical).hexdigest(),
            assets=assets,
            sources=template.sources,
            events=template.events,
            required_entries=template.required_entries,
            session_revision=template.session_revision,
            source_revision=template.source_revision,
            authority_ref=template.authority_ref,
        )
        request = request.model_copy(update={"plan_fingerprint": request.fingerprint()})
        checker = FrozenOriginalDeriveSourceChecker(
            request, lambda: self._current(state, request)
        )
        frame = OriginalDeriveFrame(
            request.operation(),
            binding,
            record.runtime_id,
            record.runtime_kind,
            request.baseline_ref,
            baseline,
            assets,
            self._counter,
            checker,
        )
        self._waits[key] = _Wait(
            scope,
            record.runtime_id,
            operation.operation_id,
            request.plan_id,
            request.plan_fingerprint,
            ref(control),
            ref(task),
        )
        state.template = None
        return frame, request

    async def _current(
        self, state: _RunTemplate, request: MemoryDeriveRequest
    ) -> SummaryTaskState:
        record = state.record
        if not state.active or record is None:
            raise ValueError("DERIVE_ORIGINAL_FRAME_REQUIRED")
        fresh = await self.execution_store.get(
            request.execution_scope.conversation.tenant_id,
            request.execution_scope.execution_id,
        )
        if (
            fresh is None
            or fresh.state != "ACTIVE"
            or fresh.runtime_id != record.runtime_id
            or fresh.context != record.context
            or getattr(fresh.context, "derive_template_json", None)
            != getattr(record.context, "derive_template_json", None)
            or fresh.deadline_epoch_seconds != record.deadline_epoch_seconds
            or time.time() >= state.deadline
        ):
            raise ValueError("DERIVE_SOURCE_AUTHORITY_MISMATCH")
        template = MemoryDeriveTemplate.model_validate_json(
            cast(str, getattr(fresh.context, "derive_template_json", None))
        )
        return SummaryTaskState(
            template.scope.conversation,
            tuple(source.metadata for source in template.sources),
            template.session_revision,
            template.source_revision,
            int(time.time()),
            template.mode,
            record.context.policy.version,
            template.authority_ref,
        )

    async def pending(
        self, tenant_id: str, execution_id: str
    ) -> MemoryDeriveRequest | None:
        waiting = self._waits.get((tenant_id, execution_id))
        if waiting is None:
            return None
        request = await self.frames.lookup_request(tenant_id, execution_id)
        if request is None or (
            request.plan_id,
            request.plan_fingerprint,
            request.runtime_id,
        ) != (waiting.plan_id, waiting.fingerprint, waiting.runtime_id):
            return None
        return request

    async def wait_for_derivation(
        self, scope: ExecutionScope, operation: ContextOperation
    ) -> None:
        waiting = self._waits.get((scope.conversation.tenant_id, scope.execution_id))
        if waiting is None:
            return
        if waiting.finished:
            return
        if (
            waiting.scope != scope
            or waiting.original_operation_id != operation.operation_id
            or waiting.task() is not asyncio.current_task()
            or waiting.control() is not current_run_control()
        ):
            raise ValueError("DERIVE_BINDING_CONFLICT")
        request = await self.pending(scope.conversation.tenant_id, scope.execution_id)
        if request is None:
            return
        try:
            if self._budget(request.budget_id) is None:
                return
        except PaidBudgetError:
            return
        deadline = min(operation.deadline_epoch_seconds, request.deadline_epoch_seconds)
        if not waiting.notified:
            waiting.notified = True
            remaining = deadline - time.time()
            if remaining <= 0:
                return
            try:
                await asyncio.wait_for(
                    self.notify(
                        waiting.runtime_id,
                        {
                            "plan_id": request.plan_id,
                            "baseline_ref": request.baseline_ref,
                        },
                    ),
                    timeout=remaining,
                )
            except TimeoutError:
                return
        while not waiting.event.is_set() and time.time() < deadline:
            control = waiting.control()
            if control is None:
                return
            control.check()
            if (
                await self.pending(scope.conversation.tenant_id, scope.execution_id)
                is None
            ):
                return
            try:
                await asyncio.wait_for(
                    waiting.event.wait(),
                    timeout=min(0.25, max(0.001, deadline - time.time())),
                )
            except TimeoutError:
                continue

    async def finish(
        self,
        tenant_id: str,
        execution_id: str,
        plan_id: str,
        plan_fingerprint: str,
        status: Literal["COMMITTED", "REJECTED"],
    ) -> None:
        waiting = self._waits.get((tenant_id, execution_id))
        request = await self.pending(tenant_id, execution_id)
        task = waiting.task() if waiting is not None else None
        control = waiting.control() if waiting is not None else None
        if (
            waiting is None
            or request is None
            or status not in {"COMMITTED", "REJECTED"}
            or (plan_id, plan_fingerprint) != (waiting.plan_id, waiting.fingerprint)
            or task is None
            or task.done()
            or control is None
        ):
            raise ValueError("DERIVE_BINDING_CONFLICT")
        control.check()
        waiting.finished = True
        waiting.event.set()
