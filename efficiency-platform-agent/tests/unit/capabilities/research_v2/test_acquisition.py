"""AcquisitionExecutor 唯一重试、预算与幂等测试。"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime

import pytest

from efficiency_platform_agent.capabilities.research.v2.acquisition import (
    AcquisitionExecutor,
    AcquisitionRuntimeContextV2,
    DiscoveryActionV2,
)
from efficiency_platform_agent.capabilities.research.v2.attempts import (
    InMemorySourceAttemptLedger,
)
from efficiency_platform_agent.contracts.research_sources_v2 import (
    DiscoveryBatchV2,
    SourceAttemptV2,
    SourceUsageV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.budget_lease import (
    BudgetLimits,
    BudgetScope,
    InMemoryBudgetLeaseRepository,
)
from efficiency_platform_agent.core.run import RunContext
from efficiency_platform_agent.providers.research.transport import ResearchFetchError
from efficiency_platform_agent.tools.external.research import (
    ExplicitDocumentFetcherRegistry,
    ExplicitSourceProviderRegistry,
    ResearchDiscoverArgumentsV2,
    StaticResearchToolScopeResolver,
    TrustedResearchToolScope,
    research_tool_entries,
)
from efficiency_platform_agent.tools.runtime.registry import ToolRegistry
from efficiency_platform_agent.tools.runtime.service import (
    ToolLeaseContext,
    ToolRuntime,
)


class _SequenceProvider:
    def __init__(
        self,
        errors: list[str | None],
        *,
        retry_after: int = 0,
        on_discover=None,
    ) -> None:
        self.errors = list(errors)
        self.retry_after = retry_after
        self.on_discover = on_discover
        self.requests = []

    async def discover(self, request) -> DiscoveryBatchV2:
        self.requests.append(request)
        if self.on_discover is not None:
            self.on_discover()
        error = self.errors.pop(0)
        attempt_id = hashlib.sha256(request.request_id.encode()).hexdigest()[:32]
        attempt = SourceAttemptV2(
            attempt_id=f"attempt-{attempt_id}",
            action_id=request.request_id,
            source_id=request.source_id,
            status="failed" if error else "success_empty",
            started_at=datetime(2026, 9, 16, tzinfo=UTC),
            finished_at=datetime(2026, 9, 16, 0, 0, 1, tzinfo=UTC),
            returned_count=0,
            filtered_count=0,
            error_code=error,
            coverage="unknown" if error else "complete",
            retry_after_seconds=self.retry_after if error else None,
            lease_id=request.lease_id,
            usage=SourceUsageV2(requests=1, returned_items=0, downloaded_bytes=0),
        )
        return DiscoveryBatchV2(
            request_id=request.request_id,
            candidates=(),
            next_cursor=None,
            completeness="unknown" if error else "complete",
            coverage="unknown" if error else "complete",
            attempts=(attempt,),
        )


class _UnusedFetcher:
    async def fetch(self, request):
        del request
        raise ResearchFetchError("CONTENT_UNAVAILABLE", "unused")


class _Backoff:
    def __init__(self) -> None:
        self.waits: list[float] = []

    async def wait(self, seconds: float) -> None:
        self.waits.append(seconds)


class _BlockingBackoff(_Backoff):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()

    async def wait(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.started.set()
        await asyncio.Event().wait()


class _CancellationSignal:
    def __init__(self) -> None:
        self.event = asyncio.Event()

    async def wait_requested(self) -> None:
        await self.event.wait()

    def is_requested(self) -> bool:
        return self.event.is_set()


class _BlockingProvider(_SequenceProvider):
    def __init__(self) -> None:
        super().__init__([None])
        self.started = asyncio.Event()

    async def discover(self, request) -> DiscoveryBatchV2:
        self.started.set()
        await asyncio.Event().wait()
        return await super().discover(request)


class _ExceptionThenProvider(_SequenceProvider):
    def __init__(self) -> None:
        super().__init__([None])
        self.failed = False

    async def discover(self, request) -> DiscoveryBatchV2:
        if not self.failed:
            self.failed = True
            self.requests.append(request)
            raise RuntimeError("secret provider body")
        return await super().discover(request)


def _executor(
    provider: _SequenceProvider,
    backoff: _Backoff,
    *,
    monotonic_clock=None,
    cancellation_signal=None,
):
    scopes = StaticResearchToolScopeResolver(
        {
            ("tenant-1", "run-1", "source-1"): TrustedResearchToolScope(
                "lease-1", "d" * 64
            ),
            ("tenant-1", "run-2", "source-1"): TrustedResearchToolScope(
                "lease-2", "e" * 64
            ),
        }
    )
    registry = ToolRegistry()
    for spec, tool in research_tool_entries(
        ExplicitSourceProviderRegistry({"source-1": provider}),
        ExplicitDocumentFetcherRegistry({"source-1": _UnusedFetcher()}),
        scopes,
    ):
        registry.register(spec, tool)
    ledger = InMemorySourceAttemptLedger()
    return (
        AcquisitionExecutor(
            ToolRuntime(registry, cancellation_signal=cancellation_signal),
            ledger,
            backoff=backoff,
            monotonic_clock=monotonic_clock or (lambda: 100.0),
        ),
        ledger,
    )


def _action(action_id: str = "action-1") -> DiscoveryActionV2:
    return DiscoveryActionV2(
        action_id,
        ResearchDiscoverArgumentsV2(
            request_id="request-1",
            source_id="source-1",
            brief_digest="a" * 64,
            query="AI",
            time_window=ResolvedTimeWindow(
                start=datetime(2026, 9, 15, tzinfo=UTC),
                end=datetime(2026, 9, 16, tzinfo=UTC),
                timezone="UTC",
                precision="day",
                original_text="yesterday",
                anchor=datetime(2026, 9, 16, tzinfo=UTC),
            ),
            cursor=None,
            limit=10,
        ),
    )


def _context(*, deadline: float = 200.0) -> AcquisitionRuntimeContextV2:
    return AcquisitionRuntimeContextV2(
        run_context=RunContext("run-1", "tenant-1", "user-1", "trace-1"),
        allowed_source_ids=frozenset({"source-1"}),
        granted_permissions=frozenset({"research:read"}),
        remaining_budget=RemainingBudget(10, 10, 10, 10, 10, 100_000),
        deadline_monotonic=deadline,
    )


@pytest.mark.asyncio
async def test_transient_failures_retry_only_in_executor_and_keep_all_attempts() -> None:
    provider = _SequenceProvider(
        ["SOURCE_TEMPORARY_FAILURE", "SOURCE_TEMPORARY_FAILURE", None]
    )
    backoff = _Backoff()
    executor, ledger = _executor(provider, backoff)
    context = _context()

    result = await executor.execute_discovery(_action(), context)

    assert result.error_code is None
    assert result.stop_reason == "COMPLETED"
    assert len(provider.requests) == 3
    assert len(result.tool_records) == 3
    attempts = await ledger.list("tenant-1", "run-1")
    assert len(attempts) == 3
    assert {attempt.action_id for attempt in attempts} == {"action-1"}
    assert backoff.waits == [0.25, 0.5]
    assert context.remaining_budget.tool_calls == 7


@pytest.mark.asyncio
async def test_same_action_replay_does_not_call_or_charge_again() -> None:
    provider = _SequenceProvider([None])
    executor, ledger = _executor(provider, _Backoff())
    context = _context()
    action = _action()

    first = await executor.execute_discovery(action, context)
    remaining_after_first = context.remaining_budget.tool_calls
    second = await executor.execute_discovery(action, context)

    assert first.replayed is False
    assert second.replayed is True
    assert len(provider.requests) == 1
    assert context.remaining_budget.tool_calls == remaining_after_first
    assert len(await ledger.list("tenant-1", "run-1")) == 1


@pytest.mark.asyncio
async def test_schema_failure_is_not_retried() -> None:
    provider = _SequenceProvider(["SOURCE_SCHEMA_INVALID", None])
    backoff = _Backoff()
    executor, _ = _executor(provider, backoff)

    result = await executor.execute_discovery(_action(), _context())

    assert result.batch is not None
    assert result.stop_reason == "COMPLETED"
    assert len(provider.requests) == 1
    assert backoff.waits == []


@pytest.mark.asyncio
async def test_retry_after_beyond_deadline_stops_without_second_dispatch() -> None:
    provider = _SequenceProvider(["SOURCE_RATE_LIMITED", None], retry_after=10)
    executor, _ = _executor(provider, _Backoff())

    result = await executor.execute_discovery(_action(), _context(deadline=105.0))

    assert result.batch is not None
    assert result.stop_reason == "RETRY_DEADLINE_EXCEEDED"
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_source_not_allowed_stops_before_tool_runtime() -> None:
    provider = _SequenceProvider([None])
    executor, _ = _executor(provider, _Backoff())
    context = _context()
    context.allowed_source_ids = frozenset()

    result = await executor.execute_discovery(_action(), context)

    assert result.error_code == "SOURCE_NOT_RUNTIME_ALLOWED"
    assert provider.requests == []


@pytest.mark.asyncio
async def test_parent_lease_charges_each_retry_once_and_replay_charges_nothing() -> None:
    provider = _SequenceProvider(
        ["SOURCE_TEMPORARY_FAILURE", "SOURCE_TEMPORARY_FAILURE", None]
    )
    executor, _ = _executor(provider, _Backoff())
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=3,
            max_bytes=10 * 1024 * 1024,
            max_cost_microunits=100,
        )
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "tool")
    context = _context()
    context.lease_context = ToolLeaseContext(
        repository, scope, "research-action", 0
    )

    first = await executor.execute_discovery(_action(), context)
    replay = await executor.execute_discovery(_action(), context)
    snapshot = await repository.snapshot(scope)

    assert first.error_code is None
    assert replay.replayed is True
    assert len(provider.requests) == 3
    assert repository.dispatched_invocation_count == 3
    assert snapshot.used.calls == 3
    assert snapshot.reserved.calls == 0


@pytest.mark.asyncio
async def test_predispatch_permission_denial_does_not_consume_local_budget() -> None:
    provider = _SequenceProvider([None])
    executor, _ = _executor(provider, _Backoff())
    context = _context()
    context.granted_permissions = frozenset()

    result = await executor.execute_discovery(_action(), context)

    assert result.error_code == "TOOL_PERMISSION_DENIED"
    assert result.tool_records == ()
    assert context.remaining_budget.tool_calls == 10
    assert provider.requests == []


@pytest.mark.asyncio
async def test_late_success_is_accounted_but_not_delivered() -> None:
    current = [100.0]
    provider = _SequenceProvider([None], on_discover=lambda: current.__setitem__(0, 201.0))
    executor, ledger = _executor(
        provider,
        _Backoff(),
        monotonic_clock=lambda: current[0],
    )

    result = await executor.execute_discovery(_action(), _context(deadline=200.0))

    assert result.batch is None
    assert result.error_code == "TOOL_TIMEOUT"
    assert result.stop_reason == "LATE_RESULT"
    assert len(provider.requests) == 1
    assert len(await ledger.list("tenant-1", "run-1")) == 1


@pytest.mark.asyncio
async def test_same_action_id_with_changed_arguments_is_rejected() -> None:
    provider = _SequenceProvider([None])
    executor, _ = _executor(provider, _Backoff())
    context = _context()
    first = await executor.execute_discovery(_action(), context)
    changed = _action()
    changed = DiscoveryActionV2(
        changed.action_id,
        changed.arguments.model_copy(update={"query": "different"}),
    )

    conflict = await executor.execute_discovery(changed, context)

    assert first.error_code is None
    assert conflict.error_code == "ACQUISITION_ACTION_CONFLICT"
    assert conflict.stop_reason == "ACTION_CONFLICT"
    assert conflict.replayed is False
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_same_action_id_is_isolated_between_runs() -> None:
    provider = _SequenceProvider([None, None])
    executor, ledger = _executor(provider, _Backoff())
    run_one = _context()
    run_two = _context()
    run_two.run_context = RunContext(
        "run-2", "tenant-1", "user-1", "trace-2"
    )

    first = await executor.execute_discovery(_action(), run_one)
    second = await executor.execute_discovery(_action(), run_two)

    assert first.replayed is False
    assert second.replayed is False
    assert len(provider.requests) == 2
    assert len(await ledger.list("tenant-1", "run-1")) == 1
    assert len(await ledger.list("tenant-1", "run-2")) == 1


@pytest.mark.asyncio
async def test_forbidden_source_failure_is_not_retried() -> None:
    provider = _SequenceProvider(["SOURCE_FORBIDDEN", None])
    backoff = _Backoff()
    executor, _ = _executor(provider, backoff)

    result = await executor.execute_discovery(_action(), _context())

    assert result.batch is not None
    assert result.batch.attempts[0].error_code == "SOURCE_FORBIDDEN"
    assert len(provider.requests) == 1
    assert backoff.waits == []


@pytest.mark.asyncio
async def test_cancellation_propagates_to_inflight_provider() -> None:
    signal = _CancellationSignal()
    provider = _BlockingProvider()
    executor, ledger = _executor(
        provider,
        _Backoff(),
        cancellation_signal=signal,
    )
    context = _context()

    running = asyncio.create_task(executor.execute_discovery(_action(), context))
    await provider.started.wait()
    signal.event.set()
    result = await asyncio.wait_for(running, timeout=1)

    assert result.error_code == "TOOL_CANCELLED"
    assert result.stop_reason == "USER_CANCELLED"
    assert result.tool_records[-1].status == "cancelled"
    assert context.remaining_budget.tool_calls == 9
    attempts = await ledger.list("tenant-1", "run-1")
    assert len(attempts) == 1
    assert attempts[0].status == "cancelled"
    assert attempts[0].action_id == "action-1"


@pytest.mark.asyncio
async def test_parent_lease_is_authoritative_when_local_budget_snapshot_is_stale() -> None:
    provider = _SequenceProvider([None])
    executor, _ = _executor(provider, _Backoff())
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=1,
            max_bytes=3 * 1024 * 1024,
            max_cost_microunits=100,
        )
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "tool")
    context = _context()
    context.remaining_budget = RemainingBudget(10, 0, 10, 10, 0, 100_000)
    context.lease_context = ToolLeaseContext(repository, scope, "research", 0)

    result = await executor.execute_discovery(_action(), context)
    snapshot = await repository.snapshot(scope)

    assert result.error_code is None
    assert len(provider.requests) == 1
    assert snapshot.used.calls == 1


@pytest.mark.asyncio
async def test_cancellation_interrupts_retry_backoff_and_preserves_attempt_audit() -> None:
    signal = _CancellationSignal()
    provider = _SequenceProvider(["SOURCE_TEMPORARY_FAILURE", None])
    backoff = _BlockingBackoff()
    executor, ledger = _executor(
        provider,
        backoff,
        cancellation_signal=signal,
    )

    running = asyncio.create_task(
        executor.execute_discovery(_action(), _context())
    )
    await backoff.started.wait()
    signal.event.set()
    result = await asyncio.wait_for(running, timeout=1)

    assert result.batch is None
    assert result.error_code == "TOOL_CANCELLED"
    assert result.stop_reason == "USER_CANCELLED"
    assert len(provider.requests) == 1
    assert len(await ledger.list("tenant-1", "run-1")) == 1


@pytest.mark.asyncio
async def test_preexisting_cancellation_stops_before_lease_dispatch() -> None:
    signal = _CancellationSignal()
    signal.event.set()
    provider = _SequenceProvider([None])
    executor, _ = _executor(
        provider,
        _Backoff(),
        cancellation_signal=signal,
    )
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=1,
            max_bytes=3 * 1024 * 1024,
            max_cost_microunits=100,
        )
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "tool")
    context = _context()
    context.lease_context = ToolLeaseContext(repository, scope, "research", 0)

    result = await executor.execute_discovery(_action(), context)

    assert result.error_code == "TOOL_CANCELLED"
    assert result.stop_reason == "USER_CANCELLED"
    assert result.tool_records == ()
    assert provider.requests == []
    assert repository.dispatched_invocation_count == 0


@pytest.mark.asyncio
async def test_tool_level_provider_failure_is_recorded_before_retry() -> None:
    provider = _ExceptionThenProvider()
    executor, ledger = _executor(provider, _Backoff())

    result = await executor.execute_discovery(_action(), _context())
    attempts = await ledger.list("tenant-1", "run-1")

    assert result.error_code is None
    assert len(provider.requests) == 2
    assert [attempt.status for attempt in attempts] == ["failed", "success_empty"]
    assert attempts[0].error_code == "SOURCE_TEMPORARY_FAILURE"
    assert all("secret" not in (record.error_code or "") for record in result.tool_records)


@pytest.mark.asyncio
async def test_later_source_failure_does_not_remove_prior_action_result() -> None:
    provider = _SequenceProvider([None, "SOURCE_FORBIDDEN"])
    executor, ledger = _executor(provider, _Backoff())
    context = _context()
    first_action = _action("action-1")
    second_base = _action("action-2")
    second_action = DiscoveryActionV2(
        second_base.action_id,
        second_base.arguments.model_copy(update={"request_id": "request-2"}),
    )

    first = await executor.execute_discovery(first_action, context)
    second = await executor.execute_discovery(second_action, context)
    replay = await executor.execute_discovery(first_action, context)

    assert first.batch is not None
    assert second.batch is not None
    assert second.batch.attempts[0].error_code == "SOURCE_FORBIDDEN"
    assert replay.replayed is True
    assert replay.batch == first.batch
    assert len(await ledger.list("tenant-1", "run-1")) == 2
