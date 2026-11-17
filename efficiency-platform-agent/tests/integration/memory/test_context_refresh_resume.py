"""生产PG登记簿+官方Saver真实验收；D13授权与事件视图为明确合成边界。"""

import asyncio
import os
import uuid
from contextlib import AsyncExitStack
from dataclasses import replace
from pathlib import Path

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection, Error, sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.errors import CheckViolation, RaiseException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from efficiency_platform_agent.core.memory import (
    ConversationScope,
    ExecutionScope,
    MemoryContextPacket,
    MemoryPolicy,
    SourceDependency,
)
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionContext,
    MemoryExecutionGrant,
    MemoryExecutionRecord,
)
from efficiency_platform_agent.core.memory_thread import (
    CheckpointLocation,
    ResumeRequest,
)
from efficiency_platform_agent.core.run import JsonObject
from efficiency_platform_agent.memory.checkpoint_erasure import CheckpointEraser
from efficiency_platform_agent.memory.execution_bindings import ThreadErasureService
from efficiency_platform_agent.orchestration.fenced_checkpoint import (
    CheckpointPayloadSerializer,
    FencedCheckpointSaver,
    OfficialPostgresInventory,
)
from efficiency_platform_agent.orchestration.postgres_checkpoint import (
    OfficialPostgresThreadStore,
)
from efficiency_platform_agent.persistence.memory_checkpoint_cipher import (
    AesGcmCheckpointBodyCipher,
)
from efficiency_platform_agent.persistence.memory_execution_registry import (
    PostgresMemoryExecutionRegistry,
)


def checkpoint_serializer():
    return CheckpointPayloadSerializer(
        AesGcmCheckpointBodyCipher(bytes(range(32)), "synthetic-checkpoint-v1")
    )


async def apply_topic(connection, topic):
    # 审定up脚本只含独立DDL，无函数体或字符串内分号。
    ddl = (Path(__file__).parents[3] / "sql/bootstrap" / topic / "02-up.sql").read_text(
        encoding="utf-8"
    )
    async with connection.transaction():
        for statement in ddl.split(";"):
            if statement.strip():
                await connection.execute(statement)


async def rollback_capability(connection):
    raw = (
        Path(__file__).parents[3]
        / "sql/bootstrap/memory_thread_capability_v1/04-rollback.sql"
    ).read_text(encoding="utf-8")
    guard, tail = raw.split("END $$;", 1)
    async with connection.transaction():
        await connection.execute(guard + "END $$;")
        for statement in tail.split(";"):
            if statement.strip():
                await connection.execute(statement)


def synthetic_record(
    now=1000, runtime="synthetic-python-run", execution="synthetic-java-exec"
):
    conversation = ConversationScope(
        "synthetic-tenant",
        "synthetic-user",
        "operations",
        "operations",
        "CONVERSATION",
        "synthetic-session",
    )
    scope = ExecutionScope(
        conversation, "synthetic-task", execution, "direct", "answer", "operations"
    )
    deps = (
        SourceDependency("CURRENT_INPUT", "synthetic-A", "1", 0, 1, 0),
        SourceDependency("CURRENT_INPUT", "synthetic-B", "1", 0, 1, 0),
    )
    packet = MemoryContextPacket(
        "synthetic-packet",
        1,
        conversation,
        scope.task_id,
        execution,
        "memory/1",
        1,
        now,
        now + 60,
        0,
        0,
        0,
        "synthetic-semantic",
        "synthetic-parent",
        (),
        deps,
    )
    context = MemoryExecutionContext(
        packet,
        MemoryPolicy("memory", "memory/1", "operations", frozenset({"operations"})),
        (MemoryExecutionGrant("direct", "operations", "answer"),),
        now + 600,
        "a" * 64,
        "b" * 64,
        "c" * 64,
    )
    return scope, MemoryExecutionRecord(
        context, runtime, "OPERATIONS", "c" * 64, now + 600, "ACTIVE", 1, 0, 0, 0
    )


def synthetic_csr_record():
    scope, record = synthetic_record(
        runtime="synthetic-csr-runtime", execution="synthetic-csr-java"
    )
    conversation = replace(
        scope.conversation,
        domain="customer-service",
        top_level_agent_id="customer-service",
    )
    scope = replace(
        scope,
        conversation=conversation,
        subtask_id="customer-service:answer_general",
        execution_agent_id="customer-service",
    )
    context = replace(
        record.context,
        packet=replace(record.context.packet, scope=conversation),
        policy=replace(
            record.context.policy,
            domain="customer-service",
            agent_ids=frozenset({"customer-service"}),
        ),
        execution_grants=(
            MemoryExecutionGrant(
                scope.subtask_id, scope.execution_agent_id, scope.purpose
            ),
        ),
    )
    return scope, replace(record, context=context, runtime_kind="CUSTOMER_SERVICE")


class SyntheticD13Store:
    """只替代D13合成快照边界，不冒称真实MySQL验收。"""

    def __init__(self, record):
        self.record = record

    async def get(self, tenant, execution):
        return (
            self.record
            if (tenant, execution)
            == (
                self.record.context.packet.scope.tenant_id,
                self.record.context.packet.execution_id,
            )
            else None
        )


class LocalPgEpochView:
    """测试专属技术事件视图，不向Java回调。"""

    def __init__(self, connection):
        self.connection = connection

    async def current(self, scope, dependencies):
        for dep in dependencies:
            row = await (
                await self.connection.execute(
                    "SELECT * FROM d16_test_source WHERE source_id=%s", (dep.source_id,)
                )
            ).fetchone()
            if (
                row is None
                or not row["active"]
                or (row["grant_epoch"], row["source_epoch"], row["deletion_epoch"])
                != (dep.grant_epoch, dep.source_epoch, dep.deletion_epoch)
            ):
                return False
        return True

    async def revoked(self, scope, source, event_id):
        row = await (
            await self.connection.execute(
                "SELECT * FROM d16_test_source WHERE source_id=%s", (source.source_id,)
            )
        ).fetchone()
        return bool(
            row
            and not row["active"]
            and row["event_id"] == event_id
            and row["source_epoch"] > source.source_epoch
        )


@pytest.fixture
async def runtime_pg():
    dsn = os.environ.get("MEMORY_IT_POSTGRES_DSN")
    if not dsn or os.environ.get("MEMORY_IT_ALLOW_SCHEMA_DDL") != "1":
        pytest.skip("需要显式本机PG DSN和本任务随机schema DDL开关")
    try:
        settings = conninfo_to_dict(dsn)
    except Error:
        pytest.fail("MEMORY_IT_POSTGRES_DSN_FORMAT_INVALID", pytrace=False)
    if settings.get("host") not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("MEMORY_IT_REQUIRES_EXPLICIT_LOOPBACK_HOST", pytrace=False)
    schema = "memory_it_thread_" + uuid.uuid4().hex[:12]
    stack = AsyncExitStack()
    created = False
    try:
        admin = await stack.enter_async_context(
            await AsyncConnection.connect(
                dsn, autocommit=True, row_factory=dict_row, connect_timeout=5
            )
        )
        await admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        created = True

        async def connect():
            return await stack.enter_async_context(
                await AsyncConnection.connect(
                    dsn,
                    options="-csearch_path=" + schema,
                    autocommit=True,
                    prepare_threshold=0,
                    row_factory=dict_row,
                    connect_timeout=5,
                )
            )

        registry_connection, saver_connection, source_connection = (
            await connect(),
            await connect(),
            await connect(),
        )
        await apply_topic(registry_connection, "memory_thread_v1")
        await source_connection.execute(
            "CREATE TABLE d16_test_source(source_id text PRIMARY KEY,grant_epoch bigint,source_epoch bigint,deletion_epoch bigint,active boolean,event_id text)"
        )
        for source in ("synthetic-A", "synthetic-B"):
            await source_connection.execute(
                "INSERT INTO d16_test_source VALUES (%s,0,1,0,true,NULL)", (source,)
            )
        saver = AsyncPostgresSaver(saver_connection)
        await saver.setup()
        scope, record = synthetic_record()
        store, source = SyntheticD13Store(record), LocalPgEpochView(source_connection)
        clock = [1001]
        inventories = (OfficialPostgresInventory(saver),)
        registry = PostgresMemoryExecutionRegistry(
            registry_connection,
            schema,
            store,
            source,
            inventories,
            clock=lambda: clock[0],
        )
        await registry.enroll(scope, record.runtime_id)
        # 实际旧GRAPH登记存在后再升级，证明DEFAULT/CHECK兼容而非空表假升级。
        await apply_topic(registry_connection, "memory_thread_capability_v1")
        upgraded = await registry._one(
            "SELECT checkpoint_mode FROM {execution} WHERE runtime_id=%s",
            (record.runtime_id,),
        )
        assert upgraded["checkpoint_mode"] == "GRAPH"
        fenced = FencedCheckpointSaver(
            saver, registry, "official", serializer=checkpoint_serializer()
        )
        eraser = CheckpointEraser(registry, (OfficialPostgresThreadStore(saver),))
        service = ThreadErasureService(registry, eraser)
        yield (
            registry,
            fenced,
            saver,
            service,
            scope,
            store,
            source_connection,
            clock,
            schema,
            connect,
        )
    finally:
        if created:
            await admin.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
        await stack.aclose()


async def seed(saver, thread):
    for namespace in ("", "subgraph"):
        config = {"configurable": {"thread_id": thread, "checkpoint_ns": namespace}}
        checkpoint = empty_checkpoint()
        checkpoint["channel_values"] = {"mixed": ["synthetic-A", "synthetic-B"]}
        checkpoint["channel_versions"] = {"mixed": "1"}
        config = await saver.aput(config, checkpoint, {}, {"mixed": "1"})
        await saver.aput_writes(
            config, [("pending", "synthetic-A/B")], "synthetic-task"
        )


async def revoke(source_connection):
    await source_connection.execute(
        "UPDATE d16_test_source SET active=false,source_epoch=2,event_id='synthetic-revoke' WHERE source_id='synthetic-A'"
    )


async def state(registry):
    return await (
        await registry.connection.execute(registry._sql("SELECT * FROM {execution}"))
    ).fetchone()


async def test_actual_registry_fences_root_child_pending_writes_then_deletes_all(
    runtime_pg,
):
    registry, saver, raw, service, scope, store, source, *_ = runtime_pg
    root = store.record.runtime_id
    child = root + ":child:synthetic"
    await registry.register_child(root, child)
    await seed(saver, root)
    await seed(saver, child)
    await revoke(source)
    prepared = await registry.prepare_cleanup(
        scope.conversation.tenant_id,
        scope.execution_id,
        "synthetic-revoke",
        1,
        (store.record.context.packet.safety_dependencies[0],),
    )
    assert prepared is not None and (await state(registry))["state"] == "REVOKED"
    with pytest.raises(PermissionError):
        await seed(saver, root)
    with pytest.raises(PermissionError):
        await registry.register_child(root, root + ":child:late")
    with pytest.raises(PermissionError):
        await saver.aget_tuple({"configurable": {"thread_id": child}})
    receipt = await service.prepare_and_erase(
        scope.conversation.tenant_id,
        scope.execution_id,
        "synthetic-revoke",
        1,
        (store.record.context.packet.safety_dependencies[0],),
    )
    assert receipt.status == "DELETED" and receipt.receipt_ref
    assert (await state(registry))["state"] == "DELETED"
    async with raw._cursor() as cursor:
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            await cursor.execute(
                sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(table))
            )
            assert (await cursor.fetchone())["n"] == 0
    assert (
        await service.prepare_and_erase(
            scope.conversation.tenant_id,
            scope.execution_id,
            "synthetic-revoke",
            1,
            (store.record.context.packet.safety_dependencies[0],),
        )
        == receipt
    )


async def test_resume_idempotency_revision_refresh_limit_and_paid_deny(runtime_pg):
    registry, _, _, _, scope, store, *_ = runtime_pg
    runtime, tenant = store.record.runtime_id, scope.conversation.tenant_id
    await registry.set_wait(runtime, tenant, "wait-8min")
    request = ResumeRequest("wait-8min", 1, 1, "same-request", "c" * 64, "cpu")
    receipt = await registry.resume(runtime, tenant, request)
    assert receipt.code == "CPU_CONFIRMED"
    assert await registry.resume(runtime, tenant, request) == receipt
    with pytest.raises(ValueError, match="409"):
        await registry.resume(
            runtime, tenant, replace(request, operation_hash="d" * 64)
        )
    assert (
        await registry.resume(
            runtime, tenant, replace(request, resume_request_id="paid", mode="paid")
        )
    ).code == "CONTINUATION_AUTH_UNSUPPORTED"
    for index in range(4):
        result = await registry.resume(
            runtime,
            tenant,
            replace(request, resume_request_id="refresh-" + str(index), mode="refresh"),
        )
        assert result.code == (
            "MEMORY_REFRESH_AUTH_UNSUPPORTED" if index < 3 else "MEMORY_REFRESH_LIMIT"
        )
    assert (await state(registry))["original_deadline"] == 1600


async def test_next_day_wait_expired_and_restart_does_not_reset_deadline(runtime_pg):
    registry, _, _, _, scope, store, _, clock, schema, connect = runtime_pg
    await registry.set_wait(
        store.record.runtime_id, scope.conversation.tenant_id, "wait-8min"
    )
    clock[0] += 86400
    restarted = PostgresMemoryExecutionRegistry(
        await connect(),
        schema,
        store,
        registry.source_authority,
        registry.inventories,
        clock=lambda: clock[0],
    )
    result = await restarted.resume(
        store.record.runtime_id,
        scope.conversation.tenant_id,
        ResumeRequest("wait-8min", 1, 1, "next-day", "c" * 64, "paid"),
    )
    assert result.code == "EXPIRED"
    assert (await state(registry))["original_deadline"] == 1600
    assert (await state(registry))["state"] == "EXPIRED"


async def test_unknown_backend_and_unknown_child_are_pending_not_fake_empty(runtime_pg):
    registry, saver, raw, service, scope, store, source, *_ = runtime_pg
    await seed(saver, store.record.runtime_id)
    await seed(raw, store.record.runtime_id + ":child:unregistered")
    await revoke(source)
    receipt = await service.prepare_and_erase(
        scope.conversation.tenant_id,
        scope.execution_id,
        "synthetic-revoke",
        1,
        (store.record.context.packet.safety_dependencies[0],),
    )
    assert receipt.status == "DELETE_PENDING" and receipt.receipt_ref is None
    assert (await state(registry))["state"] == "REVOKED"


async def test_missing_owner_never_claims_checkpoint_not_applicable(
    runtime_pg, monkeypatch
):
    registry, saver, _, service, scope, store, source, *_ = runtime_pg
    with pytest.raises(PermissionError):
        await registry.check_runtime("legacy-runtime", scope.conversation.tenant_id)
    receipt = await service.prepare_and_erase(
        scope.conversation.tenant_id,
        "legacy-execution",
        "synthetic-revoke",
        1,
        (store.record.context.packet.safety_dependencies[0],),
    )
    assert receipt.status == "DELETE_PENDING" and receipt.receipt_ref is None
    await rollback_capability(registry.connection)
    await apply_topic(registry.connection, "memory_thread_capability_v1")
    with pytest.raises(CheckViolation):
        await registry.connection.execute(
            registry._sql(
                "UPDATE {execution} SET checkpoint_mode='NONE' WHERE execution_id=%s"
            ),
            (scope.execution_id,),
        )
    csr_scope, csr_record = synthetic_csr_record()
    store.record = csr_record
    await registry.enroll_no_checkpoint(csr_scope, csr_record.runtime_id)
    await registry.check_runtime(
        csr_record.runtime_id, csr_scope.conversation.tenant_id
    )
    async with registry.guard_execution(
        csr_scope.conversation.tenant_id,
        csr_scope.execution_id,
        "NO_CHECKPOINT",
        "provider",
    ):
        pass
    with pytest.raises(PermissionError):
        await seed(saver, csr_record.runtime_id)
    with pytest.raises(PermissionError):
        await registry.register_child(
            csr_record.runtime_id, csr_record.runtime_id + ":child:forbidden"
        )
    row = await registry._one(
        "SELECT root_thread_id,checkpoint_mode,backend_ids FROM {execution} WHERE execution_id=%s",
        (csr_scope.execution_id,),
    )
    assert (
        row["root_thread_id"] is None
        and row["checkpoint_mode"] == "NONE"
        and row["backend_ids"] == []
    )
    with pytest.raises(CheckViolation):
        await registry.connection.execute(
            registry._sql(
                "UPDATE {execution} SET root_thread_id=runtime_id WHERE execution_id=%s"
            ),
            (csr_scope.execution_id,),
        )
    with pytest.raises(RaiseException, match="ROLLBACK_REQUIRES_UNUSED_NONE_MODE"):
        await rollback_capability(registry.connection)
    await revoke(source)
    args = (
        csr_scope.conversation.tenant_id,
        csr_scope.execution_id,
        "synthetic-revoke",
        1,
        (csr_record.context.packet.safety_dependencies[0],),
    )
    receipt = await service.prepare_and_erase(*args)
    assert receipt.status == "DELETED" and receipt.receipt_ref
    with pytest.raises(RaiseException, match="ROLLBACK_REQUIRES_UNUSED_NONE_MODE"):
        await rollback_capability(registry.connection)

    async def scrubbed(*args):
        raise ValueError("MEMORY_ACCESS_REVOKED")

    monkeypatch.setattr(store, "get", scrubbed)
    assert await service.prepare_and_erase(*args) == receipt


async def test_receipt_failure_keeps_delete_gate_and_retries_without_new_authorization(
    runtime_pg, monkeypatch
):
    registry, saver, _, service, scope, store, source, *_ = runtime_pg
    await seed(saver, store.record.runtime_id)
    await revoke(source)
    original = registry.finish_cleanup

    async def unavailable(*args):
        raise RuntimeError("synthetic-receipt-fault")

    monkeypatch.setattr(registry, "finish_cleanup", unavailable)
    args = (
        scope.conversation.tenant_id,
        scope.execution_id,
        "synthetic-revoke",
        1,
        (store.record.context.packet.safety_dependencies[0],),
    )
    assert (await service.prepare_and_erase(*args)).status == "DELETE_PENDING"
    assert (await state(registry))["state"] == "DELETED"
    with pytest.raises(PermissionError):
        await registry.check_runtime(
            store.record.runtime_id, scope.conversation.tenant_id
        )
    monkeypatch.setattr(registry, "finish_cleanup", original)
    assert (await service.prepare_and_erase(*args)).status == "DELETED"


async def test_source_epoch_gate_commits_before_late_saver_write(runtime_pg):
    registry, saver, _, _, _, store, source, *_ = runtime_pg
    await revoke(source)
    with pytest.raises(PermissionError, match="SOURCE_AUTHORITY"):
        await seed(saver, store.record.runtime_id)
    assert (await state(registry))["state"] == "BLOCKED"


async def test_revoke_waits_for_registered_inflight_write_lock(runtime_pg):
    registry, saver, _, _, scope, store, source, _, schema, connect = runtime_pg
    second = PostgresMemoryExecutionRegistry(
        await connect(),
        schema,
        store,
        registry.source_authority,
        registry.inventories,
        clock=lambda: 1001,
    )
    entered, release = asyncio.Event(), asyncio.Event()

    async def in_flight():
        async with registry.guard(store.record.runtime_id, "official", ""):
            entered.set()
            await release.wait()

    task = asyncio.create_task(in_flight())
    await entered.wait()
    await revoke(source)
    prepared = asyncio.create_task(
        second.prepare_cleanup(
            scope.conversation.tenant_id,
            scope.execution_id,
            "synthetic-revoke",
            1,
            (store.record.context.packet.safety_dependencies[0],),
        )
    )
    await asyncio.sleep(0)
    assert not prepared.done()
    release.set()
    await task
    assert await prepared is not None
    with pytest.raises(PermissionError):
        await seed(saver, store.record.runtime_id)


async def test_actual_registry_rejects_cross_owner_root_member_corruption(runtime_pg):
    registry, _, _, service, scope, store, source, *_ = runtime_pg
    original = store.record
    other_scope, other = synthetic_record(
        runtime="synthetic-other-python", execution="synthetic-other-java"
    )
    store.record = other
    await registry.enroll(other_scope, other.runtime_id)
    store.record = original
    # 直接构造DB可表达但生产登记器不产生的同root跨execution损坏，必须拒绝owner证明。
    await registry.connection.execute(
        registry._sql(
            "UPDATE {member} SET tenant_id=%s,execution_id=%s WHERE thread_id=%s"
        ),
        (
            other_scope.conversation.tenant_id,
            other_scope.execution_id,
            original.runtime_id,
        ),
    )
    with pytest.raises(PermissionError, match="REGISTRY_INCOMPLETE"):
        await registry.enroll(scope, original.runtime_id)
    await revoke(source)
    receipt = await service.prepare_and_erase(
        scope.conversation.tenant_id,
        scope.execution_id,
        "synthetic-revoke",
        1,
        (original.context.packet.safety_dependencies[0],),
    )
    assert receipt.status == "DELETE_PENDING" and receipt.receipt_ref is None


@pytest.mark.skipif(
    os.environ.get("MEMORY_IT_ENABLED") != "1",
    reason="需要root同时提供已审本机MySQL技术表与PG",
)
async def test_actual_mysql_d13_revocation_receipt_drives_actual_pg_thread_cleanup(
    runtime_pg,
):
    from sqlalchemy.ext.asyncio import create_async_engine

    from efficiency_platform_agent.core.memory_execution import MemoryInvalidation
    from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher
    from efficiency_platform_agent.persistence.memory_execution import (
        MySqlMemoryExecutionStore,
    )
    from efficiency_platform_agent.persistence.memory_source_epoch import (
        MySqlExecutionSourceEpochAuthority,
    )
    from efficiency_platform_agent.security.memory_packet import (
        memory_packet_digest,
        memory_packet_semantic_digest,
    )
    from tests.integration.context_control.test_memory_execution_mysql import (
        configured_url,
    )

    old_registry, _, raw, _, _, _, _, _, schema, connect = runtime_pg
    scope, synthetic = synthetic_record(
        runtime="synthetic-real-python-" + uuid.uuid4().hex,
        execution="synthetic-real-java-" + uuid.uuid4().hex,
    )
    context = replace(
        synthetic.context,
        packet_digest=memory_packet_digest(synthetic.context.packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(
            synthetic.context.packet
        ),
    )
    engine = create_async_engine(configured_url())
    try:
        store = MySqlMemoryExecutionStore(
            engine,
            MemorySnapshotCipher("synthetic-v1", {"synthetic-v1": os.urandom(32)}),
        )
        record, created = await store.claim(
            context,
            synthetic.runtime_id,
            "OPERATIONS",
            synthetic.request_fingerprint,
            synthetic.deadline_epoch_seconds,
        )
        assert created
        authority = MySqlExecutionSourceEpochAuthority(engine, store)
        registry = PostgresMemoryExecutionRegistry(
            await connect(),
            schema,
            store,
            authority,
            old_registry.inventories,
            clock=lambda: 1001,
        )
        await registry.enroll(scope, record.runtime_id)
        saver = FencedCheckpointSaver(
            raw, registry, "official", serializer=checkpoint_serializer()
        )
        child = record.runtime_id + ":child:actual"
        await registry.register_child(record.runtime_id, child)
        await seed(saver, record.runtime_id)
        await seed(saver, child)
        service = ThreadErasureService(
            registry, CheckpointEraser(registry, (OfficialPostgresThreadStore(raw),))
        )
        args = (
            scope.conversation.tenant_id,
            scope.execution_id,
            "actual-d13-event",
            1,
            (context.packet.safety_dependencies[0],),
        )
        assert (await service.prepare_and_erase(*args)).status == "DELETE_PENDING"
        stop_receipt = await store.invalidate(
            MemoryInvalidation(
                scope.conversation.tenant_id,
                scope.execution_id,
                "actual-d13-event",
                1,
                0,
                1,
                0,
            )
        )
        assert stop_receipt
        assert not await authority.current(scope, context.packet.safety_dependencies)
        assert not await authority.revoked(
            scope, context.packet.safety_dependencies[0], "missing-event"
        )
        assert await authority.revoked(
            scope, context.packet.safety_dependencies[0], "actual-d13-event"
        )
        with pytest.raises(PermissionError):
            await seed(saver, record.runtime_id)
        receipt = await service.prepare_and_erase(*args)
        assert receipt.status == "DELETED" and receipt.receipt_ref
        assert await service.prepare_and_erase(*args) == receipt
        remaining = await OfficialPostgresInventory(raw).entries(record.runtime_id)
        assert remaining == frozenset()
        assert (
            await store.get(scope.conversation.tenant_id, scope.execution_id)
        ).state == "REVOKED"
        with pytest.raises(PermissionError):
            await registry.check_runtime(
                record.runtime_id, scope.conversation.tenant_id
            )
    finally:
        await engine.dispose()


async def test_actual_pg_checkpoint_bodies_do_not_store_plaintext_markers(runtime_pg):
    (
        registry,
        saver,
        raw,
        _,
        _,
        store,
        source_connection,
        _,
        registry_schema,
        connect,
    ) = runtime_pg
    marker = "SYNTHETIC_D16_CHECKPOINT_PRIVATE_MARKER"
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"scalar": marker, "compound": {"private": marker}}
    checkpoint["channel_versions"] = {"scalar": "1", "compound": "1"}
    config = await saver.aput(
        {"configurable": {"thread_id": store.record.runtime_id, "checkpoint_ns": ""}},
        checkpoint,
        {"private": marker},
        {"scalar": "1", "compound": "1"},
    )
    await saver.aput_writes(config, [("pending", marker)], "synthetic-task")
    restored = await saver.aget_tuple(config)
    assert restored.checkpoint["channel_values"]["scalar"] == marker
    async with raw._cursor() as cursor:
        await cursor.execute(
            "SELECT checkpoint::text,metadata::text FROM checkpoints WHERE thread_id=%s",
            (store.record.runtime_id,),
        )
        for row in await cursor.fetchall():
            assert marker not in row["checkpoint"] and marker not in row["metadata"]
        for table in ("checkpoint_blobs", "checkpoint_writes"):
            await cursor.execute(
                sql.SQL("SELECT blob FROM {} WHERE thread_id=%s").format(
                    sql.Identifier(table)
                ),
                (store.record.runtime_id,),
            )
            assert all(
                marker.encode() not in bytes(row["blob"])
                for row in await cursor.fetchall()
                if row["blob"] is not None
            )
    # 官方共享blob按channel/version绑定；同一checkpoint中调换两个channel密文必须拒绝。
    async with raw._cursor() as cursor:
        await cursor.execute(
            "SELECT channel,type,blob FROM checkpoint_blobs WHERE thread_id=%s ORDER BY channel",
            (store.record.runtime_id,),
        )
        blobs = await cursor.fetchall()
        assert len(blobs) == 2
        await cursor.execute(
            "UPDATE checkpoint_blobs SET type=%s,blob=%s WHERE thread_id=%s AND channel=%s",
            (
                blobs[0]["type"],
                blobs[0]["blob"],
                store.record.runtime_id,
                blobs[1]["channel"],
            ),
        )
    with pytest.raises(ValueError, match="CHECKPOINT_BODY_UNAVAILABLE"):
        await saver.aget_tuple(config)
    async with raw._cursor() as cursor:
        await cursor.execute(
            "UPDATE checkpoint_blobs SET type=%s,blob=%s WHERE thread_id=%s AND channel=%s",
            (
                blobs[1]["type"],
                blobs[1]["blob"],
                store.record.runtime_id,
                blobs[1]["channel"],
            ),
        )
    assert (await saver.aget_tuple(config)).checkpoint["channel_values"][
        "scalar"
    ] == marker
    saved = await raw.aget_tuple(config)
    owner_scope = store.record.context.packet.scope
    original_scope = ExecutionScope(
        owner_scope,
        store.record.context.packet.task_id,
        store.record.context.packet.execution_id,
        "direct",
        "answer",
        "operations",
    )
    location = CheckpointLocation(
        original_scope, store.record.runtime_id, "", ("channel", "scalar", "1")
    )
    for wrong in (
        replace(location, checkpoint_ns="other"),
        replace(location, thread_id=location.thread_id + ":child:other"),
        replace(location, coordinate=("channel", "scalar", "2")),
        replace(
            location,
            scope=replace(
                original_scope,
                conversation=replace(owner_scope, tenant_id="synthetic-other-tenant"),
            ),
        ),
    ):
        with pytest.raises(ValueError, match="CHECKPOINT_BODY_UNAVAILABLE"):
            checkpoint_serializer().decode(
                wrong, saved.checkpoint["channel_values"]["scalar"]
            )
    next_checkpoint = empty_checkpoint() | {
        "channel_values": checkpoint["channel_values"],
        "channel_versions": checkpoint["channel_versions"],
    }
    next_config = await saver.aput(config, next_checkpoint, {"private": marker}, {})
    assert (await saver.aget_tuple(next_config)).checkpoint["channel_values"][
        "scalar"
    ] == marker
    next_saved = await raw.aget_tuple(next_config)
    async with raw._cursor() as cursor:
        await cursor.execute(
            "UPDATE checkpoints SET metadata=%s WHERE thread_id=%s AND checkpoint_id=%s",
            (Jsonb(next_saved.metadata), store.record.runtime_id, checkpoint["id"]),
        )
    with pytest.raises(ValueError, match="CHECKPOINT_BODY_UNAVAILABLE"):
        await saver.aget_tuple(config)
    async with raw._cursor() as cursor:
        await cursor.execute(
            "UPDATE checkpoints SET metadata=%s WHERE thread_id=%s AND checkpoint_id=%s",
            (Jsonb(saved.metadata), store.record.runtime_id, checkpoint["id"]),
        )
        await cursor.execute(
            "UPDATE checkpoint_writes SET task_id='synthetic-other-task' WHERE thread_id=%s AND checkpoint_id=%s",
            (store.record.runtime_id, checkpoint["id"]),
        )
    with pytest.raises(ValueError, match="CHECKPOINT_BODY_UNAVAILABLE"):
        await saver.aget_tuple(config)
    async with raw._cursor() as cursor:
        await cursor.execute(
            "UPDATE checkpoint_writes SET task_id='synthetic-task' WHERE thread_id=%s AND checkpoint_id=%s",
            (store.record.runtime_id, checkpoint["id"]),
        )

    from efficiency_platform_agent.orchestration.fenced_checkpoint import (
        FencedCheckpointStore,
        OwnedPostgresInventory,
    )
    from efficiency_platform_agent.orchestration.postgres_checkpoint import (
        PostgresCheckpointStore,
    )

    owned_schema = "agent_runtime_" + uuid.uuid4().hex[:8]
    owned_connection = await connect()
    await owned_connection.execute(
        sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(owned_schema))
    )
    try:
        await owned_connection.execute(
            sql.SQL(
                "CREATE TABLE {}.checkpoints(thread_id text NOT NULL,tenant_id text NOT NULL,checkpoint_ns text NOT NULL,checkpoint_id text NOT NULL,state jsonb NOT NULL,PRIMARY KEY(tenant_id,thread_id,checkpoint_ns))"
            ).format(sql.Identifier(owned_schema))
        )
        owned = PostgresCheckpointStore(owned_connection, owned_schema)
        scope, record = synthetic_record(
            runtime="synthetic-both-" + uuid.uuid4().hex,
            execution="synthetic-both-execution-" + uuid.uuid4().hex,
        )
        store.record = record
        both = PostgresMemoryExecutionRegistry(
            await connect(),
            registry_schema,
            store,
            registry.source_authority,
            (OfficialPostgresInventory(raw), OwnedPostgresInventory(owned)),
            clock=lambda: 1001,
        )
        await both.enroll(scope, record.runtime_id)
        official = FencedCheckpointSaver(
            raw, both, "official", serializer=checkpoint_serializer()
        )
        index = FencedCheckpointStore(owned, both, serializer=checkpoint_serializer())
        child = record.runtime_id + ":child:synthetic"
        await both.register_child(record.runtime_id, child)
        for thread in (record.runtime_id, child):
            await seed(official, thread)
            await index.save(
                thread,
                "index",
                {"private": marker},
                tenant_id=scope.conversation.tenant_id,
            )
            assert (
                await index.get(thread, "index", scope.conversation.tenant_id)
            ).state["private"] == marker
        result = await owned_connection.execute(
            sql.SQL("SELECT state::text AS state FROM {}.checkpoints").format(
                sql.Identifier(owned_schema)
            )
        )
        assert all(marker not in row["state"] for row in await result.fetchall())
        await index.get(record.runtime_id, "other", scope.conversation.tenant_id)
        raw_record = await owned.get(
            record.runtime_id, "index", scope.conversation.tenant_id
        )
        await owned.save(
            record.runtime_id,
            "other",
            raw_record.state,
            tenant_id=scope.conversation.tenant_id,
            checkpoint_id=raw_record.view.checkpoint_id,
        )
        with pytest.raises(ValueError, match="CHECKPOINT_BODY_UNAVAILABLE"):
            await index.get(record.runtime_id, "other", scope.conversation.tenant_id)
        await revoke(source_connection)
        service = ThreadErasureService(
            both, CheckpointEraser(both, (OfficialPostgresThreadStore(raw), owned))
        )
        receipt = await service.prepare_and_erase(
            scope.conversation.tenant_id,
            scope.execution_id,
            "synthetic-revoke",
            1,
            (record.context.packet.safety_dependencies[0],),
        )
        assert receipt.status == "DELETED"
        assert (
            await OfficialPostgresInventory(raw).entries(record.runtime_id)
            == frozenset()
        )
        assert (
            await OwnedPostgresInventory(owned).entries(record.runtime_id)
            == frozenset()
        )
        with pytest.raises(PermissionError):
            await index.save(
                record.runtime_id, "index", {}, tenant_id=scope.conversation.tenant_id
            )
    finally:
        await owned_connection.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(owned_schema))
        )


async def test_review_fixes_receipt_namespaces_typed_values_and_owned_binding(
    runtime_pg,
):
    from efficiency_platform_agent.orchestration.fenced_checkpoint import (
        FencedCheckpointStore,
        OwnedPostgresInventory,
    )
    from efficiency_platform_agent.orchestration.postgres_checkpoint import (
        PostgresCheckpointStore,
    )

    registry, saver, raw, service, scope, store, source, _, schema, connect = runtime_pg
    tenant = scope.conversation.tenant_id
    await registry.set_wait(store.record.runtime_id, tenant, "review-wait")
    for request_id in (
        "erase:synthetic-revoke",
        "erase:000-fake-event",
        '["memory-thread-receipt/2","ERASURE","000-fake-event"]',
    ):
        request = ResumeRequest("review-wait", 1, 1, request_id, "c" * 64, "cpu")
        receipt = await registry.resume(store.record.runtime_id, tenant, request)
        assert (
            await registry.resume(store.record.runtime_id, tenant, request) == receipt
        )
    await registry.connection.execute(
        registry._sql(
            "INSERT INTO {resume}(tenant_id,execution_id,resume_request_id,request_hash,result_code,receipt_ref) VALUES (%s,%s,'erase:000-legacy-fake',%s,'DELETE_PENDING','legacy-fake-ref')"
        ),
        (tenant, scope.execution_id, "a" * 64),
    )
    body = JsonObject(
        (
            (
                "content",
                (None, JsonObject(), JsonObject((("text", "synthetic-result"),))),
            ),
        )
    )
    checkpoint = empty_checkpoint() | {
        "channel_values": {"output": body, "strategy_payload": JsonObject()},
        "channel_versions": {"output": "1", "strategy_payload": "1"},
    }
    config = await saver.aput(
        {"configurable": {"thread_id": store.record.runtime_id, "checkpoint_ns": ""}},
        checkpoint,
        {"binding": body},
        {"output": "1", "strategy_payload": "1"},
    )
    await saver.aput_writes(config, [("pending", body)], "review-task")
    value = await saver.aget_tuple(config)
    assert value.checkpoint["channel_values"] == checkpoint["channel_values"]
    assert value.metadata["binding"] == body and value.pending_writes == [
        ("review-task", "pending", body)
    ]
    assert [entry.metadata async for entry in saver.alist(config)] == [
        {"binding": body}
    ]
    await revoke(source)
    args = (
        tenant,
        scope.execution_id,
        "synthetic-revoke",
        1,
        (store.record.context.packet.safety_dependencies[0],),
    )
    receipt = await service.prepare_and_erase(*args)
    assert receipt.status == "DELETED" and receipt.receipt_ref
    assert await service.prepare_and_erase(*args) == receipt
    assert (
        await OfficialPostgresInventory(raw).entries(store.record.runtime_id)
        == frozenset()
    )

    owned_schema = "agent_runtime_" + uuid.uuid4().hex[:8]
    connection = await connect()
    await connection.execute(
        sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(owned_schema))
    )
    try:
        await connection.execute(
            sql.SQL(
                "CREATE TABLE {}.checkpoints(thread_id text NOT NULL,tenant_id text NOT NULL,checkpoint_ns text NOT NULL,checkpoint_id text NOT NULL,state jsonb NOT NULL,PRIMARY KEY(tenant_id,thread_id,checkpoint_ns))"
            ).format(sql.Identifier(owned_schema))
        )
        next_scope, record = synthetic_record(
            runtime="review-owned-" + uuid.uuid4().hex,
            execution="review-owned-execution-" + uuid.uuid4().hex,
        )
        packet = replace(
            record.context.packet,
            safety_dependencies=(record.context.packet.safety_dependencies[1],),
        )
        store.record = replace(record, context=replace(record.context, packet=packet))
        owned = PostgresCheckpointStore(connection, owned_schema)
        inventories = (OfficialPostgresInventory(raw), OwnedPostgresInventory(owned))
        next_registry = PostgresMemoryExecutionRegistry(
            await connect(),
            schema,
            store,
            registry.source_authority,
            inventories,
            clock=lambda: 1001,
        )
        await next_registry.enroll(next_scope, record.runtime_id)
        index = FencedCheckpointStore(
            owned, next_registry, serializer=checkpoint_serializer()
        )
        binding = JsonObject((("wait_event_id", "review-owned-wait"),))
        state = {
            "output": body,
            "strategy_payload": JsonObject(),
            "resume_binding": {"wait_event_id": "review-owned-wait"},
        }
        saved = await index.save(
            record.runtime_id, "index", state, tenant_id=tenant, resume_binding=binding
        )
        restarted = PostgresMemoryExecutionRegistry(
            await connect(),
            schema,
            store,
            registry.source_authority,
            inventories,
            clock=lambda: 1001,
        )
        fresh = FencedCheckpointStore(
            PostgresCheckpointStore(connection, owned_schema),
            restarted,
            serializer=checkpoint_serializer(),
        )
        for reader in (index, fresh):
            restored = await reader.get(record.runtime_id, "index", tenant)
            assert (
                restored.state == state
                and restored.view == saved
                and restored.view.resume_binding == binding
            )
        await next_registry.connection.execute(
            next_registry._sql(
                "INSERT INTO {resume}(tenant_id,execution_id,resume_request_id,request_hash,result_code,receipt_ref) VALUES (%s,%s,'erase:review-legacy-event',%s,'DELETED','preserved-legacy-ref')"
            ),
            (tenant, next_scope.execution_id, "a" * 64),
        )
        await source.execute(
            "UPDATE d16_test_source SET active=false,source_epoch=2,event_id='review-legacy-event' WHERE source_id='synthetic-B'"
        )
        legacy_service = ThreadErasureService(
            next_registry,
            CheckpointEraser(next_registry, (OfficialPostgresThreadStore(raw), owned)),
        )
        with pytest.raises(
            ValueError, match="MEMORY_RECEIPT_PROTOCOL_UPGRADE_REQUIRED"
        ):
            await legacy_service.prepare_and_erase(
                tenant,
                next_scope.execution_id,
                "review-legacy-event",
                1,
                packet.safety_dependencies,
            )
        with pytest.raises(PermissionError):
            await fresh.get(record.runtime_id, "index", tenant)
        previous = await next_registry._one(
            "SELECT receipt_ref FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND resume_request_id='erase:review-legacy-event'",
            (tenant, next_scope.execution_id),
        )
        assert previous["receipt_ref"] == "preserved-legacy-ref"
    finally:
        await connection.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(owned_schema))
        )
