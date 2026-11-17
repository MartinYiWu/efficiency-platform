"""本机双HTTP worker共享真实MySQL，停止ACK必须来自已退出的实际任务owner。"""

import asyncio
import os
import socket
from contextlib import asynccontextmanager
from time import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine

from efficiency_platform_agent.api.memory_routes import build_memory_router
from efficiency_platform_agent.core.run_context_binding import bind_conversation_scope
from efficiency_platform_agent.harness.hr_factory import internal_hr_authorizer
from efficiency_platform_agent.harness.service import RunPipelinePreparation
from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher
from efficiency_platform_agent.persistence.memory_execution import (
    MySqlMemoryExecutionStore,
)
from efficiency_platform_agent.persistence.mysql_runtime import (
    MySqlRunEventStore,
    MySqlRunRepository,
)
from tests.integration.context_control.test_memory_execution_mysql import (
    configured_url,
    context,
)
from tests.unit.harness.test_memory_run_binding import request, service

pytestmark = pytest.mark.skipif(
    os.environ.get("MEMORY_IT_ENABLED") != "1", reason="需root显式本机隔离MySQL"
)


@asynccontextmanager
async def running(app):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    listener.setblocking(False)
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("MEMORY_IT_HTTP_START_FAILED")
                await asyncio.sleep(0.01)
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{listener.getsockname()[1]}",
            timeout=15,
            trust_env=False,
        ) as client:
            yield client
    finally:
        server.should_exit = True
        try:
            async with asyncio.timeout(10):
                await task
        finally:
            if not task.done():
                task.cancel()
            listener.close()


@pytest.mark.asyncio
async def test_actual_two_worker_http_never_acks_foreign_active_or_completed_task():
    first_engine, second_engine = (
        create_async_engine(configured_url()),
        create_async_engine(configured_url()),
    )
    cipher = MemorySnapshotCipher("isolated", {"isolated": os.urandom(32)})
    first_store, second_store = (
        MySqlMemoryExecutionStore(first_engine, cipher),
        MySqlMemoryExecutionStore(second_engine, cipher),
    )
    owner, observer = (
        service(MySqlRunRepository(first_engine, cipher)),
        service(MySqlRunRepository(second_engine, cipher)),
    )
    owner.event_store, observer.event_store = (
        MySqlRunEventStore(first_engine),
        MySqlRunEventStore(second_engine),
    )
    ids = SimpleNamespace(
        new_run_id=lambda: uuid4().hex, new_event_id=lambda: uuid4().hex
    )
    owner.id_generator = observer.id_generator = ids
    owner.clock = observer.clock = SimpleNamespace(
        now_epoch_ms=lambda: int(time() * 1000)
    )
    owner.memory_execution_store, observer.memory_execution_store = (
        first_store,
        second_store,
    )
    memory = context()
    # HTTP Header需ASCII；身份值保持精确，不通过日志或错误输出。
    from dataclasses import replace

    from efficiency_platform_agent.security.memory_packet import (
        memory_packet_digest,
        memory_packet_semantic_digest,
    )

    packet = replace(
        memory.packet,
        scope=replace(memory.packet.scope, tenant_id="isolated-stop-tenant"),
    )
    memory = replace(
        memory,
        packet=packet,
        packet_digest=memory_packet_digest(packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(packet),
    )
    tenant, execution = memory.packet.scope.tenant_id, memory.packet.execution_id
    original = request(
        request_id=uuid4().hex, tenant_id=tenant, user_id=memory.packet.scope.user_id
    )
    entered, release = asyncio.Event(), asyncio.Event()

    async def prepare(pipeline):
        entered.set()
        await release.wait()
        return RunPipelinePreparation(original)

    secret = uuid4().hex + uuid4().hex
    apps = []
    for runtime, store in ((owner, first_store), (observer, second_store)):

        async def stop(record, target=runtime):
            await target.stop_memory_execution(
                record.runtime_id, record.context.packet.scope.tenant_id
            )

        app = FastAPI()
        app.include_router(
            build_memory_router(store, internal_hr_authorizer(secret), stop)
        )
        apps.append(app)
    try:
        with bind_conversation_scope(memory.packet.scope, memory_context=memory):
            view = await owner.create_and_schedule_pipeline(original, prepare)
        await asyncio.wait_for(entered.wait(), 5)
        body = {
            "event_id": uuid4().hex,
            "expected_execution_revision": packet.execution_revision,
            "grant_epoch": 1,
            "source_epoch": 2,
            "deletion_epoch": 1,
        }
        headers = {"Authorization": "Bearer " + secret, "X-Tenant-ID": tenant}
        path = f"/internal/v1/memory/executions/{execution}/invalidate"
        async with running(apps[0]) as first_http, running(apps[1]) as second_http:
            blocked = await second_http.post(path, json=body, headers=headers)
            assert (
                blocked.status_code == 503
                and blocked.json()["detail"] == "MEMORY_STOP_PENDING"
            )
            assert (await second_store.get(tenant, execution)).state == "REVOKED"
            assert any(not task.done() for task in owner._background_tasks)
            stopping = asyncio.create_task(
                first_http.post(path, json=body, headers=headers)
            )
            await asyncio.sleep(0.05)
            assert not stopping.done()
            release.set()
            confirmed = await stopping
            assert (
                confirmed.status_code == 200
                and confirmed.json()["target"] == "AGENT_STOP"
            )
            assert not owner._background_tasks
            assert (
                await owner.repository.get(view.run_id, tenant)
            ).status.value == "cancelled"
            still_unproved = await second_http.post(path, json=body, headers=headers)
            assert (
                still_unproved.status_code == 503
                and still_unproved.json()["detail"] == "MEMORY_STOP_PENDING"
            )
    finally:
        release.set()
        await owner.wait_for_background_tasks()
        await first_engine.dispose()
        await second_engine.dispose()
