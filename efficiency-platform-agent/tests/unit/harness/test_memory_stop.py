"""取消状态不等于后台协程已退出；仅等待目标执行，不能阻塞其他用户。"""

import asyncio

import pytest

from efficiency_platform_agent.contracts.requests import CancelRunRequestV1
from efficiency_platform_agent.harness.service import RunPipelinePreparation
from tests.unit.harness.test_memory_run_binding import request, service


@pytest.mark.asyncio
async def test_memory_stop_waits_own_background_task_even_if_cancelled_state_is_persisted():
    runtime = service()
    record, _ = await runtime._create_queued(request())
    release = asyncio.Event()
    unrelated_release = asyncio.Event()
    own = asyncio.create_task(
        release.wait(), name="agent-run-pipeline:" + record.run_id
    )
    unrelated = asyncio.create_task(
        unrelated_release.wait(), name="agent-run:other-user"
    )
    runtime._register_background_task(record, own)
    runtime._background_tasks.add(unrelated)
    await runtime.cancel_run(record.run_id, CancelRunRequestV1(tenant_id="t"))
    try:
        stop = asyncio.create_task(runtime.stop_memory_execution(record.run_id, "t"))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not stop.done()
        release.set()
        await asyncio.wait_for(stop, 1)
        assert own.done()
        assert not unrelated.done()
    finally:
        release.set()
        unrelated_release.set()
        await asyncio.gather(own, unrelated)


@pytest.mark.asyncio
async def test_missing_run_is_not_acknowledged_as_already_stopped():
    runtime = service()
    with pytest.raises(ValueError, match="MEMORY_STOP_UNAVAILABLE"):
        await runtime.stop_memory_execution("missing", "t")


@pytest.mark.asyncio
async def test_other_worker_cannot_ack_owners_live_or_completed_pipeline():
    owner = service()
    observer = service(owner.repository)
    observer.event_store = owner.event_store
    observer.id_generator = owner.id_generator
    entered, release = asyncio.Event(), asyncio.Event()
    original = request()

    async def prepare(context):
        entered.set()
        await release.wait()
        return RunPipelinePreparation(original)

    view = await owner.create_and_schedule_pipeline(original, prepare)
    await entered.wait()
    try:
        with pytest.raises(ValueError, match="MEMORY_STOP_PENDING"):
            await observer.stop_memory_execution(view.run_id, "t")
        assert any(not task.done() for task in owner._background_tasks)
    finally:
        release.set()
        await owner.wait_for_background_tasks()
    await owner.stop_memory_execution(view.run_id, "t")
    with pytest.raises(ValueError, match="MEMORY_STOP_PENDING"):
        await observer.stop_memory_execution(view.run_id, "t")


@pytest.mark.asyncio
async def test_on_queued_window_is_not_exit_proof_before_background_registration():
    runtime = service()
    entered, release = asyncio.Event(), asyncio.Event()
    run_ids = []

    async def on_queued(view):
        run_ids.append(view.run_id)
        entered.set()
        await release.wait()

    async def prepare(context):
        raise AssertionError("已取消运行不得进入prepare")

    submit = asyncio.create_task(
        runtime.create_and_schedule_pipeline(request(), prepare, on_queued=on_queued)
    )
    await entered.wait()
    try:
        assert not runtime._background_tasks
        with pytest.raises(ValueError, match="MEMORY_STOP_PENDING"):
            await runtime.stop_memory_execution(run_ids[0], "t")
    finally:
        release.set()
        await submit
        await runtime.wait_for_background_tasks()
    await runtime.stop_memory_execution(run_ids[0], "t")


@pytest.mark.asyncio
async def test_customer_stop_without_original_task_is_pending_even_for_terminal_view():
    from types import SimpleNamespace
    from uuid import uuid4

    from efficiency_platform_agent.agents.customer_service.service import (
        CustomerServiceRunService,
    )
    from efficiency_platform_agent.agents.customer_service.state import RunStatus

    runtime = CustomerServiceRunService(None, None, None)
    run_id = uuid4()
    with pytest.raises(ValueError, match="MEMORY_STOP_PENDING"):
        await runtime.stop_memory_execution(run_id)
    runtime._runs[run_id] = SimpleNamespace(
        task=None, view=SimpleNamespace(status=RunStatus.CANCELLED)
    )
    with pytest.raises(ValueError, match="MEMORY_STOP_PENDING"):
        await runtime.stop_memory_execution(run_id)
