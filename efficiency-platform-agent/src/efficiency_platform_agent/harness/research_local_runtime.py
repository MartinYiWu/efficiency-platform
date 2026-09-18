"""本地研究按可信 Run 装配唯一 LangGraph Service，并复用父预算账本。"""

from __future__ import annotations

import asyncio
import hashlib
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal

from efficiency_platform_agent.contracts.research_local_runtime_v2 import (
    LocalResearchRunKeyV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    BudgetSnapshotV2,
    ResearchBriefV2,
    ResearchOutcomeV2,
    ResearchRuntimeContextV2,
)
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.budget_execution import (
    BudgetExecutionBinding,
    bind_budget_execution,
    current_budget_execution_binding,
)
from efficiency_platform_agent.core.budget_lease import (
    BudgetLimits,
    BudgetScope,
    InMemoryBudgetLeaseRepository,
)
from efficiency_platform_agent.orchestration.research_v2.service import (
    LangGraphResearchServiceV2,
)
from efficiency_platform_agent.persistence.research_local_memory import (
    LocalResearchRunStore,
)

from .service import RunPipelineContext


def build_local_research_binding(
    *,
    tenant_id: str,
    run_id: str,
    lease_id: str,
    remaining: RemainingBudget,
    now: datetime,
    max_calls: int = 60,
    max_bytes: int = 20 * 1024 * 1024,
    clock_ms: Callable[[], int] | None = None,
) -> BudgetExecutionBinding:
    """在 Run 首次创建时构造唯一内存父账本；较严 Harness 配额优先。"""
    timeout_ms = min(180_000, remaining.timeout_ms)
    if timeout_ms <= 0 or max_calls <= 0 or max_bytes <= 0:
        raise ValueError("LOCAL_RESEARCH_BUDGET_INVALID")
    limits = BudgetLimits(
        max_calls=min(60, max_calls, remaining.tool_calls),
        max_bytes=min(20 * 1024 * 1024, max_bytes),
        max_input_tokens=remaining.input_tokens,
        max_output_tokens=remaining.output_tokens,
        max_cost_microunits=remaining.cost_microunits,
        deadline_epoch_ms=int(now.timestamp() * 1000) + timeout_ms,
        output_token_reserve=math.ceil(remaining.output_tokens / 4),
        output_time_reserve_ms=35_000,
    )
    return BudgetExecutionBinding(
        port=InMemoryBudgetLeaseRepository(limits, clock_ms=clock_ms),
        scope=BudgetScope(tenant_id, run_id, "research", "parent"),
        lease_id=lease_id,
        authorization_scope_digest=hashlib.sha256(
            f"local-live:{tenant_id}:{run_id}:{lease_id}".encode()
        ).hexdigest(),
    )


@dataclass(frozen=True, slots=True)
class LocalResearchExecutionV2:
    """给后续正式阶段工厂的显式运行依赖；不携带 API 对象。"""

    key: LocalResearchRunKeyV2
    brief: ResearchBriefV2
    store: LocalResearchRunStore
    binding: BudgetExecutionBinding
    budget: BudgetSnapshotV2
    deadline: datetime
    is_cancelled: Callable[[], Awaitable[bool]]
    wait_cancelled: Callable[[], Awaitable[None]]
    max_http_requests: int = 60
    max_body_requests: int = 30
    max_concurrency: int = 4
    max_host_concurrency: int = 1
    max_collection_rounds: int = 3


@dataclass(slots=True)
class _BoundRun:
    key: LocalResearchRunKeyV2
    binding: BudgetExecutionBinding
    deadline: datetime
    is_cancelled: Callable[[], Awaitable[bool]]
    wait_cancelled: Callable[[], Awaitable[None]]
    task: asyncio.Task[ResearchOutcomeV2] | None = None


class RunScopedResearchServiceV2:
    """每个 Run 只创建一次正式 Service，重试共享同次执行及终态结果。"""

    def __init__(
        self,
        *,
        store: LocalResearchRunStore,
        service_factory: Callable[
            [LocalResearchExecutionV2], LangGraphResearchServiceV2
        ],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.store, self.service_factory, self.now = store, service_factory, now
        self._runs: dict[tuple[str, str, str, int], _BoundRun] = {}
        self._lock = asyncio.Lock()
        self._workers: set[asyncio.Task[ResearchOutcomeV2]] = set()

    async def put_brief(self, brief: ResearchBriefV2) -> None:
        """Brief 只使用已登记的事实库快照，不新增无限期副本。"""
        async with self._lock:
            await self._expire_runs()
            bound = self._runs[self._index(brief)]
            if (await self.store.get(bound.key)).brief != brief:
                raise ValueError("LOCAL_RESEARCH_BRIEF_CONFLICT")

    async def get_brief(
        self, tenant_id: str, task_id: str, run_id: str | None = None
    ) -> ResearchBriefV2 | None:
        async with self._lock:
            await self._expire_runs()
            matches = [
                bound
                for (tenant, run, task, _), bound in self._runs.items()
                if tenant == tenant_id
                and task == task_id
                and (run_id is None or run == run_id)
            ]
            if len(matches) != 1:
                return None
            return (await self.store.get(matches[0].key)).brief

    async def prepare_research_run(
        self,
        brief: ResearchBriefV2,
        pipeline: RunPipelineContext,
        *,
        user_id: str,
        conversation_id: str,
    ) -> None:
        binding = current_budget_execution_binding()
        if binding is None:
            raise ValueError("LOCAL_RESEARCH_BINDING_REQUIRED")
        trusted = brief.trusted_context
        key = LocalResearchRunKeyV2(
            tenant_id=trusted.tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            run_id=pipeline.run_id,
            task_id=trusted.task_id,
            revision=brief.intent_revision,
        )
        await self.register_run(
            key,
            brief,
            binding=binding,
            deadline=self.now()
            + timedelta(
                milliseconds=min(180_000, pipeline.remaining_budget.timeout_ms)
            ),
            is_cancelled=pipeline.is_cancelled,
            wait_cancelled=pipeline.wait_cancelled,
        )

    async def register_run(
        self,
        key: LocalResearchRunKeyV2,
        brief: ResearchBriefV2,
        *,
        binding: BudgetExecutionBinding,
        deadline: datetime,
        is_cancelled: Callable[[], Awaitable[bool]],
        wait_cancelled: Callable[[], Awaitable[None]],
    ) -> None:
        trusted = brief.trusted_context
        if (key.tenant_id, key.run_id, key.task_id, key.revision) != (
            trusted.tenant_id,
            trusted.run_id,
            trusted.task_id,
            brief.intent_revision,
        ):
            raise ValueError("LOCAL_RESEARCH_IDENTITY_MISMATCH")
        if (binding.scope.tenant_id, binding.scope.run_id, binding.lease_id) != (
            trusted.tenant_id,
            trusted.run_id,
            trusted.budget_lease_id,
        ) or binding.scope.source_account_id is not None:
            raise ValueError("LOCAL_RESEARCH_BINDING_MISMATCH")
        snapshot = await binding.port.snapshot(binding.scope)
        limits = snapshot.limits
        if (
            limits.deadline_epoch_ms is None
            or limits.max_calls > 60
            or limits.output_time_reserve_ms < 35000
            or limits.output_token_reserve < math.ceil(limits.max_output_tokens / 4)
        ):
            raise ValueError("LOCAL_RESEARCH_BUDGET_NOT_BOUNDED")
        deadline = min(
            deadline,
            self.now() + timedelta(seconds=180),
            datetime.fromtimestamp(limits.deadline_epoch_ms / 1000, UTC),
        )
        async with self._lock:
            await self._expire_runs()
            index = self._index(brief)
            existing = self._runs.get(index)
            if existing is not None:
                if existing.key != key or existing.binding is not binding:
                    raise ValueError("LOCAL_RESEARCH_RUN_CONFLICT")
                await self.store.create(key, brief)
                return
            await self.store.create(key, brief)
            self._runs[index] = _BoundRun(
                key, binding, deadline, is_cancelled, wait_cancelled
            )

    async def research(
        self, brief: ResearchBriefV2, runtime_context: ResearchRuntimeContextV2
    ) -> ResearchOutcomeV2:
        async with self._lock:
            await self._expire_runs()
            bound = self._runs[self._index(brief)]
            facts = await self.store.get(bound.key)
            if (
                facts.brief != brief
                or bound.binding.lease_id != brief.trusted_context.budget_lease_id
            ):
                raise ValueError("LOCAL_RESEARCH_BRIEF_CONFLICT")
            if bound.task is None:
                deadline = min(bound.deadline, runtime_context.deadline)
                bounded_context = runtime_context.model_copy(
                    update={"deadline": deadline}
                )
                bound.task = asyncio.create_task(
                    self._execute(bound, brief, bounded_context)
                )
            task = bound.task
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if not task.done():
                await self._mark_terminal(bound.binding, "cancelled")
                task.cancel()
            raise

    async def _execute(
        self,
        bound: _BoundRun,
        brief: ResearchBriefV2,
        context: ResearchRuntimeContextV2,
    ) -> ResearchOutcomeV2:
        async with self.store.reference(bound.key):
            worker: asyncio.Task[ResearchOutcomeV2] | None = None
            cancellation: asyncio.Future[None] | None = None
            try:
                if await bound.is_cancelled():
                    raise asyncio.CancelledError
                seconds = (context.deadline - self.now()).total_seconds()
                if seconds <= 0:
                    raise TimeoutError("LOCAL_RESEARCH_HARD_DEADLINE")
                snapshot = await bound.binding.port.snapshot(bound.binding.scope)
                bound.binding.update_version(snapshot.version)
                execution = LocalResearchExecutionV2(
                    key=bound.key,
                    brief=brief,
                    store=self.store,
                    binding=bound.binding,
                    budget=BudgetSnapshotV2(
                        lease_id=bound.binding.lease_id,
                        version=snapshot.version,
                        remaining_calls=max(
                            0,
                            snapshot.limits.max_calls
                            - snapshot.used.calls
                            - snapshot.reserved.calls,
                        ),
                        remaining_bytes=max(
                            0,
                            snapshot.limits.max_bytes
                            - snapshot.used.bytes
                            - snapshot.reserved.bytes,
                        ),
                    ),
                    deadline=context.deadline,
                    is_cancelled=bound.is_cancelled,
                    wait_cancelled=bound.wait_cancelled,
                    max_http_requests=min(60, snapshot.limits.max_calls),
                )
                service = self.service_factory(execution)
                if not isinstance(service, LangGraphResearchServiceV2):
                    raise TypeError("LOCAL_RESEARCH_REQUIRES_LANGGRAPH_SERVICE")
                with bind_budget_execution(bound.binding):
                    worker = asyncio.create_task(
                        self._invoke(service, bound.key, brief, context)
                    )
                self._workers.add(worker)
                worker.add_done_callback(self._workers.discard)
                cancellation = asyncio.ensure_future(bound.wait_cancelled())
                done, _ = await asyncio.wait(
                    (worker, cancellation),
                    timeout=seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancellation in done or await bound.is_cancelled():
                    raise asyncio.CancelledError
                if worker not in done or self.now() >= context.deadline:
                    raise TimeoutError("LOCAL_RESEARCH_HARD_DEADLINE")
                outcome = worker.result()
                await self.store.finish(
                    bound.key,
                    status="failed" if outcome.outcome == "FAILED" else "completed",
                    outcome=outcome,
                )
                await self._mark_terminal(bound.binding, "terminal")
                return outcome
            except asyncio.CancelledError:
                await self._mark_terminal(bound.binding, "cancelled")
                await self.store.finish(bound.key, status="cancelled")
                raise
            except TimeoutError:
                await self._mark_terminal(bound.binding, "terminal")
                await self.store.finish(bound.key, status="timed_out")
                raise
            except Exception:
                await self._mark_terminal(bound.binding, "terminal")
                await self.store.finish(bound.key, status="failed")
                raise
            finally:
                pending = [task for task in (worker, cancellation) if task is not None]
                for task in pending:
                    if not task.done():
                        task.cancel()
                    task.add_done_callback(_consume_completion)

    async def _invoke(
        self,
        service: LangGraphResearchServiceV2,
        key: LocalResearchRunKeyV2,
        brief: ResearchBriefV2,
        context: ResearchRuntimeContextV2,
    ) -> ResearchOutcomeV2:
        """迟到调用保留活动引用，退出后才允许 TTL 回收。"""
        async with self.store.reference(key):
            return await service.research(brief, context)

    async def expire(self, now: datetime) -> int:
        async with self._lock:
            count = await self.store.expire(now)
            await self._expire_runs()
            return count

    async def _expire_runs(self) -> None:
        retained = await self.store.retained_keys()
        for index, bound in tuple(self._runs.items()):
            if bound.key not in retained and (bound.task is None or bound.task.done()):
                del self._runs[index]

    @staticmethod
    async def _mark_terminal(
        binding: BudgetExecutionBinding, reason: Literal["cancelled", "terminal"]
    ) -> None:
        """输出阶段共用同一账本，但具有独立 usage_key，须同时冻结。"""
        await binding.port.mark_scope_terminal(binding.scope, reason)
        await binding.port.mark_scope_terminal(
            replace(binding.scope, stage="output"), reason
        )

    @staticmethod
    def _index(brief: ResearchBriefV2) -> tuple[str, str, str, int]:
        trusted = brief.trusted_context
        return trusted.tenant_id, trusted.run_id, trusted.task_id, brief.intent_revision


def _consume_completion[T](task: asyncio.Future[T]) -> None:
    """迟到结果只由原账本结算；取出异常避免异步警告，绝不交付。"""
    if not task.cancelled():
        task.exception()
