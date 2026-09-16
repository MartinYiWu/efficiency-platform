"""进程内 Run 与事件适配器的并发、CAS 和租户隔离契约。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from efficiency_platform_agent.core.budget import BudgetGuard
from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.core.run import ExecutionBudget, RunRequest
from efficiency_platform_agent.core.runtime import (
    RunEventRecord,
    RunRecord,
    UsageSnapshot,
)
from efficiency_platform_agent.persistence.in_memory import (
    FixedClock,
    InMemoryPersistenceError,
    InMemoryRunEventStore,
    InMemoryRunRepository,
    SequenceIdGenerator,
)


def _record(
    run_id: str = "run-1", tenant_id: str = "tenant-1", request_id: str = "req-1"
) -> RunRecord:
    """构造最小有效 Run 快照。"""
    budget = ExecutionBudget(3, 2, 100, 100, 1_000, 100)
    return RunRecord(
        run_id=run_id,
        request=RunRequest(request_id, tenant_id, "user-1", "问题"),
        status=RunStatus.CREATED,
        strategy=None,
        budget=budget,
        budget_state=BudgetGuard().start(budget, now_epoch_ms=1_000),
        usage=UsageSnapshot(estimated=True),
        version=1,
    )


def _event(
    event_id: str = "event-1",
    run_id: str = "run-1",
    tenant_id: str = "tenant-1",
    sequence: int = 1,
) -> RunEventRecord:
    """构造最小有效运行事件。"""
    return RunEventRecord(
        event_id=event_id,
        event_type="run_started",
        run_id=run_id,
        tenant_id=tenant_id,
        sequence=sequence,
        occurred_at_epoch_ms=1_001 + sequence,
        status=RunStatus.RUNNING,
    )


@pytest.mark.asyncio
async def test_repository_create_rejects_duplicate_and_keeps_tenant_isolation() -> None:
    repository = InMemoryRunRepository()
    await repository.create(_record())
    with pytest.raises(InMemoryPersistenceError) as duplicate:
        await repository.create(_record())
    assert duplicate.value.code == "RUN_ALREADY_EXISTS"
    assert await repository.get("run-1", "tenant-2") is None
    assert await repository.get_by_request_id("req-1", "tenant-2") is None


@pytest.mark.asyncio
async def test_repository_save_uses_atomic_compare_and_swap() -> None:
    repository = InMemoryRunRepository()
    source = _record()
    await repository.create(source)
    updated = source.transition(RunStatus.QUEUED)
    await repository.save(updated, expected_version=1)
    with pytest.raises(InMemoryPersistenceError) as conflict:
        await repository.save(updated, expected_version=1)
    assert conflict.value.code == "RUN_VERSION_CONFLICT"
    current = await repository.get("run-1", "tenant-1")
    assert current is not None
    assert current.version == 2


@pytest.mark.asyncio
async def test_repository_returns_immutable_snapshot() -> None:
    repository = InMemoryRunRepository()
    await repository.create(_record())
    snapshot = await repository.get("run-1", "tenant-1")
    assert snapshot is not None
    with pytest.raises(FrozenInstanceError):
        snapshot.version = 2  # type: ignore[misc]


@pytest.mark.asyncio
async def test_event_store_enforces_monotonic_sequence_and_unique_event_id() -> None:
    store = InMemoryRunEventStore()
    await store.append(_event(sequence=1))
    with pytest.raises(InMemoryPersistenceError) as sequence_conflict:
        await store.append(_event(event_id="event-2", sequence=3))
    assert sequence_conflict.value.code == "EVENT_SEQUENCE_CONFLICT"
    await store.append(_event(event_id="event-2", sequence=2))
    with pytest.raises(InMemoryPersistenceError) as id_conflict:
        await store.append(_event(event_id="event-2", run_id="run-2"))
    assert id_conflict.value.code == "EVENT_ID_CONFLICT"


@pytest.mark.asyncio
async def test_event_list_after_is_strict_cursor_and_isolates_runs_and_tenants() -> (
    None
):
    store = InMemoryRunEventStore()
    await store.append(_event(sequence=1))
    await store.append(_event(event_id="event-2", sequence=2))
    await store.append(_event(event_id="event-other", run_id="run-2", sequence=1))
    await store.append(
        _event(event_id="event-tenant", tenant_id="tenant-2", sequence=1)
    )

    events = await store.list_after("run-1", "tenant-1", after_sequence=1)
    assert tuple(event.sequence for event in events) == (2,)
    tenant_events = await store.list_after("run-1", "tenant-2", after_sequence=0)
    assert tuple(event.event_id for event in tenant_events) == ("event-tenant",)
    assert await store.list_after("run-missing", "tenant-1", after_sequence=0) == ()


@pytest.mark.asyncio
async def test_clock_and_id_generator_are_deterministic() -> None:
    clock = FixedClock(1234)
    assert clock.now_epoch_ms() == 1234
    generator = SequenceIdGenerator()
    assert generator.new_run_id() == "run-1"
    assert generator.new_run_id() == "run-2"
    assert generator.new_event_id() == "event-1"
