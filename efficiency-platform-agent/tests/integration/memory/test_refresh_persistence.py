"""RF03本机专属双库主链；不安装运行帧或Provider发送许可。"""

import json
import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import AsyncConnection, sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from efficiency_platform_agent.core.memory import ExecutionScope
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionContext,
    MemoryExecutionGrant,
)
from efficiency_platform_agent.core.memory_refresh import (
    MemoryContextResume,
    ResumeMode,
    WaitPhase,
)
from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher
from efficiency_platform_agent.persistence.memory_execution import (
    MySqlMemoryExecutionStore,
)
from efficiency_platform_agent.persistence.memory_execution_registry import (
    PostgresMemoryExecutionRegistry,
)
from efficiency_platform_agent.persistence.memory_source_epoch import (
    MySqlExecutionSourceEpochAuthority,
)
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)
from tests.integration.context_control.test_memory_execution_mysql import configured_url

pytestmark = pytest.mark.skipif(
    os.environ.get("MEMORY_IT_ENABLED") != "1", reason="需root本机隔离双库"
)


@pytest.fixture
async def refresh_case():
    dsn = os.environ.get("MEMORY_IT_POSTGRES_DSN")
    if not dsn or os.environ.get("MEMORY_IT_ALLOW_SCHEMA_DDL") != "1":
        pytest.skip("需本机PG及专属schema DDL开关")
    if conninfo_to_dict(dsn).get("host") not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("MEMORY_IT_LOOPBACK_REQUIRED", pytrace=False)
    schema = "memory_it_rf03_" + uuid4().hex[:10]
    engine = create_async_engine(configured_url())
    async with await AsyncConnection.connect(
        dsn, autocommit=True, row_factory=dict_row
    ) as admin:
        await admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            async with await AsyncConnection.connect(
                dsn,
                options="-csearch_path=" + schema,
                autocommit=True,
                row_factory=dict_row,
            ) as pg:
                for topic in (
                    "memory_thread_v1",
                    "memory_thread_capability_v1",
                    "memory_thread_refresh_v1",
                ):
                    ddl = (
                        Path(__file__).parents[3]
                        / "sql/bootstrap"
                        / topic
                        / "02-up.sql"
                    ).read_text(encoding="utf-8")
                    await pg.execute(ddl, prepare=False)
                raw = json.loads(
                    (
                        Path(__file__).parents[2]
                        / "fixtures/memory_refresh_transport.json"
                    ).read_text(encoding="utf-8")
                )["original_context"]
                context = MemoryExecutionContext.from_metadata(
                    raw["authorization"] | {"packet": raw["packet"]}
                )
                conversation = replace(
                    context.packet.scope,
                    domain="customer-service",
                    top_level_agent_id="customer-service",
                )
                packet = replace(
                    context.packet, execution_id=uuid4().hex, scope=conversation
                )
                context = replace(
                    context,
                    packet=packet,
                    policy=replace(
                        context.policy,
                        domain="customer-service",
                        agent_ids=frozenset({"customer-service"}),
                    ),
                    execution_grants=(
                        MemoryExecutionGrant(
                            "answer", "customer-service", "assistant_response"
                        ),
                    ),
                    packet_digest=memory_packet_digest(packet),
                    semantic_snapshot_digest=memory_packet_semantic_digest(packet),
                )
                scope = ExecutionScope(
                    conversation,
                    packet.task_id,
                    packet.execution_id,
                    "answer",
                    "assistant_response",
                    "customer-service",
                )
                store = MySqlMemoryExecutionStore(
                    engine, MemorySnapshotCipher("rf03", {"rf03": bytes(range(32))})
                )
                runtime, clock = uuid4().hex, [150]
                record, _ = await store.claim(
                    context, runtime, "CUSTOMER_SERVICE", "c" * 64, 200
                )
                registry = PostgresMemoryExecutionRegistry(
                    pg,
                    schema,
                    store,
                    MySqlExecutionSourceEpochAuthority(engine, store),
                    (),
                    clock=lambda: clock[0],
                    checkpoint_capability="NONE_ONLY",
                )
                await registry.enroll_no_checkpoint(scope, runtime)
                clock[0] = 161
                yield scope, record, store, registry, clock
        finally:
            await engine.dispose()
            await admin.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


@pytest.mark.asyncio
async def test_real_none_wait_and_refresh_keep_original_identity(refresh_case):
    from efficiency_platform_agent.memory.context_refresh import (
        MemoryContextRefreshService,
    )
    from efficiency_platform_agent.persistence.memory_context_refresh import (
        MySqlMemoryContextRefreshStore,
    )

    scope, record, store, registry, clock = refresh_case
    service = MemoryContextRefreshService(
        registry, MySqlMemoryContextRefreshStore(store)
    )
    wait_id = await service.begin_wait_intent(
        scope, record.runtime_id, "operation", 1, WaitPhase.BEFORE_PREPARE
    )
    assert await service.get_wait(scope.conversation, scope.execution_id) is None
    await service.finish_wait(scope.conversation, scope.execution_id, wait_id)
    wait = await service.get_wait(scope.conversation, scope.execution_id)
    packet = replace(
        record.context.packet, packet_revision=2, issued_at=161, expires_at=190
    )
    refreshed = replace(
        record.context, packet=packet, packet_digest=memory_packet_digest(packet)
    )
    command = MemoryContextResume(
        wait_id,
        1,
        1,
        uuid4().hex,
        record.request_fingerprint,
        ResumeMode.REFRESH,
        False,
        "memory-context-resume/2",
        "operation",
        None,
        1,
        wait.expected_current_context_fingerprint,
        refreshed,
    )
    receipt = await service.resume(scope.conversation, scope.execution_id, command)
    assert receipt.code == "CONTEXT_REFRESHED" and receipt.refresh_count == 1
    assert receipt.dispatch_allowed is False
    assert (
        await service.resume(scope.conversation, scope.execution_id, command) == receipt
    )
    current = await store.get(scope.conversation.tenant_id, scope.execution_id)
    assert current.context == refreshed
    assert current.deadline_epoch_seconds == record.deadline_epoch_seconds
    async with store.engine.connect() as conn:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT context_fingerprint,current_context_fingerprint FROM agent_memory_execution WHERE tenant_id=:tenant AND execution_id=:execution"
                    ),
                    {
                        "tenant": scope.conversation.tenant_id.encode(),
                        "execution": scope.execution_id.encode(),
                    },
                )
            )
            .mappings()
            .one()
        )
    assert row["context_fingerprint"] == wait.expected_current_context_fingerprint
    assert row["current_context_fingerprint"] == receipt.current_context_fingerprint
    assert await service.get_wait(scope.conversation, scope.execution_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("fault_point", ["after_a", "after_b", "after_c"])
async def test_real_restart_same_candidate_never_counts_twice(
    refresh_case, fault_point
):
    from efficiency_platform_agent.memory.context_refresh import (
        MemoryContextRefreshService,
    )
    from efficiency_platform_agent.persistence.memory_context_refresh import (
        MySqlMemoryContextRefreshStore,
    )

    scope, record, store, registry, clock = refresh_case

    async def fail(point):
        if point == fault_point:
            raise RuntimeError("RF03_FAULT")

    service = MemoryContextRefreshService(
        registry, MySqlMemoryContextRefreshStore(store), fault_hook=fail
    )
    wait_id = await service.begin_wait_intent(
        scope, record.runtime_id, "operation", 1, WaitPhase.BEFORE_PREPARE
    )
    await service.finish_wait(scope.conversation, scope.execution_id, wait_id)
    wait = await service.get_wait(scope.conversation, scope.execution_id)
    packet = replace(
        record.context.packet, packet_revision=2, issued_at=161, expires_at=190
    )
    refreshed = replace(
        record.context, packet=packet, packet_digest=memory_packet_digest(packet)
    )
    command = MemoryContextResume(
        wait_id,
        1,
        1,
        uuid4().hex,
        record.request_fingerprint,
        ResumeMode.REFRESH,
        False,
        "memory-context-resume/2",
        "operation",
        None,
        1,
        wait.expected_current_context_fingerprint,
        refreshed,
    )
    with pytest.raises(RuntimeError, match="RF03_FAULT"):
        await service.resume(scope.conversation, scope.execution_id, command)
    restarted = MemoryContextRefreshService(
        registry, MySqlMemoryContextRefreshStore(store)
    )
    receipt = await restarted.resume(scope.conversation, scope.execution_id, command)
    assert receipt.code == "CONTEXT_REFRESHED"
    assert receipt.refresh_count == 1 and receipt.dispatch_allowed is False
    assert (
        await restarted.resume(scope.conversation, scope.execution_id, command)
        == receipt
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault_point,expected_phase",
    [("after_a", "EXPIRED_UNAPPLIED"), ("after_b", "APPLIED_EXPIRED")],
)
async def test_real_candidate_expiry_never_enables_dispatch(
    refresh_case, fault_point, expected_phase
):
    from efficiency_platform_agent.memory.context_refresh import (
        MemoryContextRefreshService,
    )
    from efficiency_platform_agent.persistence.memory_context_refresh import (
        MySqlMemoryContextRefreshStore,
    )

    scope, record, store, registry, clock = refresh_case

    async def expire(point):
        if point == fault_point:
            clock[0] = 191
            raise RuntimeError("RF03_FAULT")

    service = MemoryContextRefreshService(
        registry, MySqlMemoryContextRefreshStore(store), fault_hook=expire
    )
    wait_id = await service.begin_wait_intent(
        scope, record.runtime_id, "operation", 1, WaitPhase.BEFORE_PREPARE
    )
    await service.finish_wait(scope.conversation, scope.execution_id, wait_id)
    wait = await service.get_wait(scope.conversation, scope.execution_id)
    packet = replace(
        record.context.packet, packet_revision=2, issued_at=161, expires_at=190
    )
    refreshed = replace(
        record.context, packet=packet, packet_digest=memory_packet_digest(packet)
    )
    command = MemoryContextResume(
        wait_id,
        1,
        1,
        uuid4().hex,
        record.request_fingerprint,
        ResumeMode.REFRESH,
        False,
        "memory-context-resume/2",
        "operation",
        None,
        1,
        wait.expected_current_context_fingerprint,
        refreshed,
    )
    with pytest.raises(RuntimeError, match="RF03_FAULT"):
        await service.resume(scope.conversation, scope.execution_id, command)
    restarted = MemoryContextRefreshService(
        registry, MySqlMemoryContextRefreshStore(store)
    )
    receipt = await restarted.resume(scope.conversation, scope.execution_id, command)
    assert (
        receipt.candidate_phase == expected_phase and receipt.dispatch_allowed is False
    )
    assert receipt.refresh_count == 1
    assert (
        await restarted.resume(scope.conversation, scope.execution_id, command)
        == receipt
    )
    if expected_phase == "APPLIED_EXPIRED":
        assert receipt.current_packet_revision == 2
        assert receipt.state == "BLOCKED" and receipt.next_wait_event_id is None
    else:
        assert (
            receipt.current_packet_revision == 1 and receipt.state == "WAITING_CONTEXT"
        )


@pytest.mark.asyncio
async def test_real_result_capture_without_trusted_send_permit_is_closed(refresh_case):
    from efficiency_platform_agent.persistence.context_manifest import (
        MySqlContextManifestStore,
    )

    _, _, store, _, _ = refresh_case
    manifests = MySqlContextManifestStore(store.engine)
    with pytest.raises(PermissionError, match="MEMORY_REFRESH_CAPABILITY_UNSUPPORTED"):
        await manifests.capture_result_once(None, None, None, None)


@pytest.mark.asyncio
async def test_real_stop_aborts_v2_pending_before_revocation(refresh_case):
    from efficiency_platform_agent.core.memory_execution import MemoryInvalidation
    from efficiency_platform_agent.memory.context_refresh import MemoryContextRefreshService
    from efficiency_platform_agent.persistence.memory_context_refresh import MySqlMemoryContextRefreshStore

    scope, record, store, registry, _ = refresh_case
    async def fail(point):
        if point == "after_a":
            raise RuntimeError("RF03_FAULT")
    service = MemoryContextRefreshService(registry, MySqlMemoryContextRefreshStore(store), fault_hook=fail)
    wait_id = await service.begin_wait_intent(scope, record.runtime_id, "operation", 1, WaitPhase.BEFORE_PREPARE)
    await service.finish_wait(scope.conversation,scope.execution_id,wait_id)
    wait = await service.get_wait(scope.conversation,scope.execution_id)
    packet=replace(record.context.packet,packet_revision=2,issued_at=161,expires_at=190)
    command=MemoryContextResume(wait_id,1,1,uuid4().hex,record.request_fingerprint,ResumeMode.REFRESH,False,"memory-context-resume/2","operation",None,1,wait.expected_current_context_fingerprint,replace(record.context,packet=packet,packet_digest=memory_packet_digest(packet)))
    with pytest.raises(RuntimeError,match="RF03_FAULT"):
        await service.resume(scope.conversation,scope.execution_id,command)
    event=MemoryInvalidation(scope.conversation.tenant_id,scope.execution_id,uuid4().hex,1,1,3,1)
    await store.invalidate(event)
    prepared=await registry.prepare_cleanup(scope.conversation.tenant_id,scope.execution_id,event.event_id,1,tuple(dict.fromkeys(record.context.packet.safety_dependencies)))
    assert prepared is not None
    row=await registry._one("SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s",(scope.conversation.tenant_id,scope.execution_id))
    assert row["state"] == "REVOKED" and row["refresh_count"] == 1
    assert all(row[key] is None for key in ("pending_resume_request_id","pending_candidate_digest","pending_packet_revision","pending_context_fingerprint"))
    receipt=await MemoryContextRefreshService(registry,MySqlMemoryContextRefreshStore(store)).resume(scope.conversation,scope.execution_id,command)
    assert receipt.candidate_phase == "ABORTED" and receipt.state == "REVOKED" and receipt.dispatch_allowed is False
    erased=await registry.erase_if_no_checkpoint(scope,event.event_id,1)
    assert erased.status == "DELETED"
