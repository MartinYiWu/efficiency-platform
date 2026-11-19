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
async def refresh_case(request):
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
                    tenant_id=getattr(request, "param", context.packet.scope.tenant_id),
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
                    engine,
                    MemorySnapshotCipher("rf03", {"rf03": bytes(range(32))}),
                    refresh_schema_required=True,
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

    scope, record, store, registry, _clock = refresh_case
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

    scope, record, store, registry, _clock = refresh_case

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

    scope, record, store, registry, _clock = refresh_case

    async def expire(point):
        if point == fault_point:
            _clock[0] = 191
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
    from efficiency_platform_agent.memory.context_refresh import (
        MemoryContextRefreshService,
    )
    from efficiency_platform_agent.persistence.memory_context_refresh import (
        MySqlMemoryContextRefreshStore,
    )

    scope, record, store, registry, _ = refresh_case

    async def fail(point):
        if point == "after_a":
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
        replace(
            record.context, packet=packet, packet_digest=memory_packet_digest(packet)
        ),
    )
    with pytest.raises(RuntimeError, match="RF03_FAULT"):
        await service.resume(scope.conversation, scope.execution_id, command)
    event = MemoryInvalidation(
        scope.conversation.tenant_id, scope.execution_id, uuid4().hex, 1, 1, 3, 1
    )
    await store.invalidate(event)
    prepared = await registry.prepare_cleanup(
        scope.conversation.tenant_id,
        scope.execution_id,
        event.event_id,
        1,
        tuple(dict.fromkeys(record.context.packet.safety_dependencies)),
    )
    assert prepared is not None
    row = await registry._one(
        "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
        (scope.conversation.tenant_id, scope.execution_id),
    )
    assert row["state"] == "REVOKED" and row["refresh_count"] == 1
    assert all(
        row[key] is None
        for key in (
            "pending_resume_request_id",
            "pending_candidate_digest",
            "pending_packet_revision",
            "pending_context_fingerprint",
        )
    )
    receipt = await MemoryContextRefreshService(
        registry, MySqlMemoryContextRefreshStore(store)
    ).resume(scope.conversation, scope.execution_id, command)
    assert (
        receipt.candidate_phase == "ABORTED"
        and receipt.state == "REVOKED"
        and receipt.dispatch_allowed is False
    )
    erased = await registry.erase_if_no_checkpoint(scope, event.event_id, 1)
    assert erased.status == "DELETED"


async def _prepare_result_capture(
    refresh_case,
    fault_hook=None,
    *,
    mark_sending=True,
    operation_id="result-operation",
    input_hash="d" * 64,
):
    from efficiency_platform_agent.core.context_control import (
        ContextManifest,
        TokenMeasurement,
        WindowDecision,
    )
    from efficiency_platform_agent.core.context_ports import ContextOperation
    from efficiency_platform_agent.core.memory_execution import MemorySendPermit
    from efficiency_platform_agent.core.run import (
        ProviderMessage,
        ProviderResult,
        ProviderUsage,
    )
    from efficiency_platform_agent.persistence.context_manifest import (
        MySqlContextManifestStore,
    )

    scope, record, store, _registry, _clock = refresh_case
    packet = record.context.packet
    manifest = ContextManifest(
        "manifest",
        scope,
        operation_id,
        "answer",
        1,
        "offline-model/1",
        "prompt/1",
        "tool/1",
        "result/1",
        "tokenizer/1",
        "serialization/1",
        packet.policy_version,
        packet.packet_id,
        packet.packet_revision,
        1,
        packet.safety_dependencies,
        packet.safety_dependencies,
        (),
        TokenMeasurement(1, (("full", 1),), "offline", True),
        WindowDecision(100, 1, 1, "ALLOW"),
        1,
        0,
        input_hash,
    )
    operation = ContextOperation(
        manifest.operation_id, 1, record.deadline_epoch_seconds, False
    )
    permit = MemorySendPermit(
        scope,
        record.runtime_id,
        operation.operation_id,
        1,
        manifest.canonical_request_hmac,
        manifest.manifest_id,
        packet.packet_id,
        packet.packet_revision,
        record.context.packet_digest,
        record.execution_revision,
        record.deadline_epoch_seconds,
        uuid4().hex,
    )

    class BoundAuthority:
        async def validate(self, candidate):
            return candidate is permit

    manifests = MySqlContextManifestStore(
        store.engine, memory_execution_store=store, result_fault_hook=fault_hook
    )
    manifests.install_result_authority(BoundAuthority())
    await manifests.save_manifest_once(manifest, operation)
    if mark_sending:
        assert await manifests.mark_sending(manifest, operation)
    result = ProviderResult(
        "1",
        ProviderMessage("assistant", "synthetic result"),
        ProviderUsage(1, 2, 0, 0, 0),
    )
    return manifests, manifest, operation, permit, result


@pytest.mark.asyncio
async def test_real_result_body_and_success_are_atomic_and_idempotent(refresh_case):
    manifests, manifest, operation, permit, result = await _prepare_result_capture(
        refresh_case
    )
    _, _, _store, _registry, clock = refresh_case
    clock[0] = 170
    ref = await manifests.capture_result_once(manifest, operation, permit, result)
    assert (
        await manifests.capture_result_once(manifest, operation, permit, result) == ref
    )
    receipt = await manifests.get_operation_receipt(
        manifest.scope, manifest.operation_id
    )
    assert receipt.status == "SUCCEEDED" and receipt.receipt_ref == ref
    assert await manifests.get_captured_result(manifest, operation, permit) == result
    changed = replace(result, message=replace(result.message, content="different"))
    with pytest.raises(ValueError, match="MEMORY_RESULT_CONFLICT"):
        await manifests.capture_result_once(manifest, operation, permit, changed)
    with pytest.raises(PermissionError, match="MEMORY_REFRESH_CAPABILITY_UNSUPPORTED"):
        await manifests.capture_result_once(
            manifest, operation, replace(permit, permit_ref=uuid4().hex), result
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("point", ["after_result_insert", "after_result_receipt"])
async def test_real_result_capture_fault_preserves_sent_without_body(
    refresh_case, point
):
    async def fail(actual):
        if actual == point:
            raise RuntimeError("RF03_RESULT_FAULT")

    manifests, manifest, operation, permit, result = await _prepare_result_capture(
        refresh_case, fail
    )
    with pytest.raises(RuntimeError, match="RF03_RESULT_FAULT"):
        await manifests.capture_result_once(manifest, operation, permit, result)
    receipt = await manifests.get_operation_receipt(
        manifest.scope, manifest.operation_id
    )
    assert receipt.status == "SENT"
    with pytest.raises(ValueError, match="MEMORY_RESULT_UNAVAILABLE"):
        await manifests.get_captured_result(manifest, operation, permit)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault_point", ["after_a", "after_c"])
async def test_real_historical_wait_keeps_frozen_binding_for_same_candidate(
    refresh_case, fault_point
):
    from efficiency_platform_agent.memory.context_refresh import (
        MemoryContextRefreshService,
    )
    from efficiency_platform_agent.persistence.memory_context_refresh import (
        MySqlMemoryContextRefreshStore,
    )

    scope, record, store, registry, _ = refresh_case

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
    original = await service.get_wait(scope.conversation, scope.execution_id)
    packet = replace(
        record.context.packet, packet_revision=2, issued_at=161, expires_at=190
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
        original.expected_current_context_fingerprint,
        replace(
            record.context, packet=packet, packet_digest=memory_packet_digest(packet)
        ),
    )
    with pytest.raises(RuntimeError, match="RF03_FAULT"):
        await service.resume(scope.conversation, scope.execution_id, command)
    restarted = MemoryContextRefreshService(
        registry, MySqlMemoryContextRefreshStore(store)
    )
    historical = await restarted.get_wait(
        scope.conversation, scope.execution_id, wait_id
    )
    assert replace(historical, refresh_count=original.refresh_count) == original
    receipt = await restarted.resume(scope.conversation, scope.execution_id, command)
    assert receipt.refresh_count == 1 and receipt.dispatch_allowed is False
    assert (
        await restarted.resume(scope.conversation, scope.execution_id, command)
        == receipt
    )


@pytest.mark.asyncio
async def test_real_send_lease_packet_ttl_does_not_block_wait_or_result_scope(
    refresh_case,
):
    from efficiency_platform_agent.core.memory_execution import MemoryInvalidation

    manifests, manifest, operation, permit, result = await _prepare_result_capture(
        refresh_case
    )
    scope, _record, store, registry, _clock = refresh_case
    with pytest.raises(PermissionError, match="MEMORY_PACKET_EXPIRED"):
        async with registry.send_lease_execution(
            scope.conversation.tenant_id,
            scope.execution_id,
            "NO_CHECKPOINT",
            "provider",
        ):
            pytest.fail("expired packet must not send")
    row = await registry._one(
        "SELECT state FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
        (scope.conversation.tenant_id, scope.execution_id),
    )
    assert row["state"] == "ACTIVE"
    with pytest.raises(PermissionError, match="MEMORY_REFRESH_CAPABILITY_UNSUPPORTED"):
        async with registry.result_lease_execution(
            scope.conversation.tenant_id,
            scope.execution_id,
            "NO_CHECKPOINT",
            "provider",
            permit,
        ):
            pytest.fail("unregistered permit authority")

    class IssuedAuthority:
        def validate_issued(self, candidate):
            return candidate is permit

    registry.install_result_authority(IssuedAuthority())
    async with registry.result_lease_execution(
        scope.conversation.tenant_id,
        scope.execution_id,
        "NO_CHECKPOINT",
        "provider",
        permit,
    ):
        await manifests.capture_result_once(manifest, operation, permit, result)
    event = MemoryInvalidation(
        scope.conversation.tenant_id, scope.execution_id, uuid4().hex, 1, 1, 3, 1
    )
    await store.invalidate(event)
    with pytest.raises(PermissionError):
        async with registry.result_lease_execution(
            scope.conversation.tenant_id,
            scope.execution_id,
            "NO_CHECKPOINT",
            "provider",
            permit,
        ):
            pytest.fail("revocation must deny result continuation")


@pytest.mark.asyncio
async def test_real_scrub_removes_wait_refresh_and_result_bodies(refresh_case):
    from efficiency_platform_agent.core.memory_execution import MemoryInvalidation
    from efficiency_platform_agent.memory.context_refresh import (
        MemoryContextRefreshService,
    )
    from efficiency_platform_agent.persistence.memory_cleanup import (
        MySqlMemoryCleanupJournal,
    )
    from efficiency_platform_agent.persistence.memory_context_refresh import (
        MySqlMemoryContextRefreshStore,
    )

    manifests, manifest, operation, permit, result = await _prepare_result_capture(
        refresh_case
    )
    scope, record, store, registry, _ = refresh_case
    await manifests.capture_result_once(manifest, operation, permit, result)
    service = MemoryContextRefreshService(
        registry, MySqlMemoryContextRefreshStore(store)
    )
    wait_id = await service.begin_wait_intent(
        scope, record.runtime_id, "operation", 1, WaitPhase.BEFORE_PREPARE
    )
    await service.finish_wait(scope.conversation, scope.execution_id, wait_id)
    wait = await service.get_wait(scope.conversation, scope.execution_id)
    packet = replace(
        record.context.packet, packet_revision=2, issued_at=161, expires_at=190
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
        replace(
            record.context, packet=packet, packet_digest=memory_packet_digest(packet)
        ),
    )
    await service.resume(scope.conversation, scope.execution_id, command)
    current = await store.get(scope.conversation.tenant_id, scope.execution_id)
    event = MemoryInvalidation(
        scope.conversation.tenant_id, scope.execution_id, uuid4().hex, 1, 1, 3, 1
    )
    dependencies = tuple(dict.fromkeys(record.context.packet.safety_dependencies))
    cleanup = MySqlMemoryCleanupJournal(store.engine, refresh_schema_required=True)

    async def scrub_runtime(_record):
        return True

    cleanup.runtime_scrubber = scrub_runtime
    stop_ref = await cleanup.revoke(event, dependencies, current)
    await cleanup.confirm(event, dependencies, "AGENT_STOP", stop_ref)
    await cleanup.confirm(event, dependencies, "THREADS", "threads-complete")
    assert await cleanup.scrub(event, dependencies, current)
    async with store.engine.connect() as conn:
        rows = (
            (
                await conn.execute(
                    text(
                        "SELECT record_kind,body_ciphertext,body_nonce,body_scrub_event_id FROM agent_memory_context_refresh WHERE tenant_id=:tenant AND execution_id=:execution"
                    ),
                    {
                        "tenant": scope.conversation.tenant_id.encode(),
                        "execution": scope.execution_id.encode(),
                    },
                )
            )
            .mappings()
            .all()
        )
    assert {row["record_kind"] for row in rows} == {"WAIT", "REFRESH", "RESULT"}
    assert all(
        row["body_ciphertext"] is None
        and row["body_nonce"] is None
        and bytes(row["body_scrub_event_id"]).decode() == event.event_id
        for row in rows
    )
    with pytest.raises(PermissionError):
        await manifests.capture_result_once(manifest, operation, permit, result)
    assert (await cleanup.receipts(event, dependencies))["SNAPSHOT"]


async def _begin_refresh_candidate(
    refresh_case, *, fault_hook=None, frame_verifier=None
):
    from efficiency_platform_agent.memory.context_refresh import (
        MemoryContextRefreshService,
    )
    from efficiency_platform_agent.persistence.memory_context_refresh import (
        MySqlMemoryContextRefreshStore,
    )

    scope, record, store, registry, _ = refresh_case
    service = MemoryContextRefreshService(
        registry,
        MySqlMemoryContextRefreshStore(store),
        fault_hook=fault_hook,
        frame_verifier=frame_verifier,
    )
    wait_id = await service.begin_wait_intent(
        scope, record.runtime_id, "operation", 1, WaitPhase.BEFORE_PREPARE
    )
    await service.finish_wait(scope.conversation, scope.execution_id, wait_id)
    wait = await service.get_wait(scope.conversation, scope.execution_id)
    packet = replace(
        record.context.packet, packet_revision=2, issued_at=161, expires_at=170
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
        replace(
            record.context, packet=packet, packet_digest=memory_packet_digest(packet)
        ),
    )
    return service, wait, command


@pytest.mark.asyncio
@pytest.mark.parametrize("fault_point", ["after_b", "after_mysql_settlement"])
async def test_real_live_none_frame_applied_expiry_keeps_one_successor(
    refresh_case, fault_point
):
    from efficiency_platform_agent.memory.context_refresh import (
        MemoryContextRefreshService,
    )
    from efficiency_platform_agent.persistence.memory_context_refresh import (
        MySqlMemoryContextRefreshStore,
    )

    scope, record, store, registry, clock = refresh_case

    async def live_frame(wait, runtime):
        return runtime == record.runtime_id and wait.execution_id == scope.execution_id

    async def expire(point):
        if point == "after_b":
            clock[0] = 171
        if point == fault_point:
            raise RuntimeError("RF03_FAULT")

    service, original, command = await _begin_refresh_candidate(
        refresh_case, fault_hook=expire, frame_verifier=live_frame
    )
    with pytest.raises(RuntimeError, match="RF03_FAULT"):
        await service.resume(scope.conversation, scope.execution_id, command)
    restarted = MemoryContextRefreshService(
        registry, MySqlMemoryContextRefreshStore(store), frame_verifier=live_frame
    )
    receipt = await restarted.resume(scope.conversation, scope.execution_id, command)
    assert (
        receipt.candidate_phase == "APPLIED_EXPIRED"
        and receipt.state == "WAITING_CONTEXT"
    )
    assert (
        receipt.next_wait_event_id not in {None, original.wait_event_id}
        and receipt.dispatch_allowed is False
    )
    successor = await restarted.get_wait(scope.conversation, scope.execution_id)
    assert successor.wait_event_id == receipt.next_wait_event_id
    assert (
        successor.expected_packet_revision == 2
        and successor.wait_phase == original.wait_phase
    )
    assert (
        successor.expected_current_context_fingerprint
        == receipt.current_context_fingerprint
    )
    assert (
        await restarted.resume(scope.conversation, scope.execution_id, command)
        == receipt
    )
    async with store.engine.connect() as conn:
        count = (
            await conn.execute(
                text(
                    "SELECT COUNT(*) FROM agent_memory_context_refresh WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='WAIT'"
                ),
                {
                    "tenant": scope.conversation.tenant_id.encode(),
                    "execution": scope.execution_id.encode(),
                },
            )
        ).scalar_one()
    assert count == 2
    assert (
        await restarted.get_wait_outcome(
            scope.conversation, scope.execution_id, original.wait_event_id
        )
        == receipt
    )
    assert (
        await restarted.get_wait_receipt(
            scope.conversation, scope.execution_id, original.wait_event_id
        )
        is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault_point,phase",
    [("after_a", "EXPIRED_UNAPPLIED"), ("after_b", "APPLIED_EXPIRED")],
)
async def test_real_third_candidate_expiry_ends_without_successor(
    refresh_case, fault_point, phase
):
    scope, _, _, registry, clock = refresh_case
    async with registry._transaction():
        for _ in range(2):
            await registry.connection.execute(
                registry._sql(
                    "UPDATE {execution} SET refresh_count=refresh_count+1 WHERE tenant_id=%s AND execution_id=%s"
                ),
                (scope.conversation.tenant_id, scope.execution_id),
            )

    async def expire(point):
        if point == fault_point:
            clock[0] = 171
            raise RuntimeError("RF03_FAULT")

    service, _, command = await _begin_refresh_candidate(
        refresh_case, fault_hook=expire
    )
    with pytest.raises(RuntimeError, match="RF03_FAULT"):
        await service.resume(scope.conversation, scope.execution_id, command)
    service.fault_hook = None
    receipt = await service.resume(scope.conversation, scope.execution_id, command)
    assert receipt.refresh_count == 3 and receipt.candidate_phase == phase
    assert (
        receipt.state == "BLOCKED"
        and receipt.next_wait_event_id is None
        and receipt.dispatch_allowed is False
    )
    assert (
        await service.resume(scope.conversation, scope.execution_id, command) == receipt
    )
    with pytest.raises(ValueError, match="CONTEXT_REFRESH_LIMIT"):
        await service.resume(
            scope.conversation,
            scope.execution_id,
            replace(command, resume_request_id=uuid4().hex),
        )


@pytest.mark.asyncio
async def test_real_original_deadline_after_a_aborts_pending_without_install(
    refresh_case,
):
    scope, record, store, registry, clock = refresh_case

    async def expire(point):
        if point == "after_a":
            clock[0] = 201
            raise RuntimeError("RF03_FAULT")

    service, _, command = await _begin_refresh_candidate(
        refresh_case, fault_hook=expire
    )
    with pytest.raises(RuntimeError, match="RF03_FAULT"):
        await service.resume(scope.conversation, scope.execution_id, command)
    service.fault_hook = None
    receipt = await service.resume(scope.conversation, scope.execution_id, command)
    assert (
        receipt.code == "EXECUTION_EXPIRED"
        and receipt.candidate_phase == "ABORTED"
        and receipt.state == "EXPIRED"
    )
    assert receipt.refresh_count == 1 and receipt.dispatch_allowed is False
    current = await store.get(scope.conversation.tenant_id, scope.execution_id)
    assert current.context == record.context and current.deadline_epoch_seconds == 200
    row = await registry._one(
        "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
        (scope.conversation.tenant_id, scope.execution_id),
    )
    assert row["state"] == "EXPIRED" and row["pending_resume_request_id"] is None
    assert (
        await service.resume(scope.conversation, scope.execution_id, command) == receipt
    )


@pytest.mark.asyncio
async def test_real_succeeded_without_result_body_never_backfills(refresh_case):
    manifests, manifest, operation, permit, result = await _prepare_result_capture(
        refresh_case
    )
    assert await manifests.record_receipt(manifest, "SUCCEEDED", "legacy-success")
    with pytest.raises(ValueError, match="MEMORY_RESULT_UNAVAILABLE"):
        await manifests.capture_result_once(manifest, operation, permit, result)
    with pytest.raises(ValueError, match="MEMORY_RESULT_UNAVAILABLE"):
        await manifests.get_captured_result(manifest, operation, permit)


@pytest.mark.asyncio
async def test_real_restart_default_key_change_keeps_original_execution_key(
    refresh_case,
):
    scope, record, store, _registry, _ = refresh_case
    rotated = MemorySnapshotCipher(
        "new", {"rf03": bytes(range(32)), "new": bytes(reversed(range(32)))}
    )
    store.cipher = rotated
    service, _, command = await _begin_refresh_candidate(refresh_case)
    receipt = await service.resume(scope.conversation, scope.execution_id, command)
    assert receipt.code == "CONTEXT_REFRESHED"
    restarted = MySqlMemoryExecutionStore(
        store.engine, rotated, refresh_schema_required=True
    )
    restored = await restarted.get(scope.conversation.tenant_id, scope.execution_id)
    assert (
        restored.context == command.refreshed_context and restored.key_version == "rf03"
    )
    assert (
        restored.request_fingerprint == record.request_fingerprint
        and restored.deadline_epoch_seconds == record.deadline_epoch_seconds
    )
    assert (
        await service.resume(scope.conversation, scope.execution_id, command) == receipt
    )
    missing_old = MySqlMemoryExecutionStore(
        store.engine,
        MemorySnapshotCipher("new", {"new": bytes(reversed(range(32)))}),
        refresh_schema_required=True,
    )
    with pytest.raises(ValueError, match="MEMORY_SNAPSHOT_UNAVAILABLE"):
        await missing_old.get(scope.conversation.tenant_id, scope.execution_id)


@pytest.mark.asyncio
async def test_real_execution_manifest_audit_keeps_sent_history_across_operations(
    refresh_case,
):
    _, old_manifest, _, _, _ = await _prepare_result_capture(
        refresh_case, operation_id="old-intent", input_hash="e" * 64
    )
    scope, _, store, registry, clock = refresh_case
    service, _, command = await _begin_refresh_candidate(refresh_case)
    receipt = await service.resume(scope.conversation, scope.execution_id, command)
    assert receipt.dispatch_allowed is False
    current = await store.get(scope.conversation.tenant_id, scope.execution_id)
    _, new_manifest, _, _, _ = await _prepare_result_capture(
        (scope, current, store, registry, clock), operation_id="current-answer"
    )
    assert await service.validate_execution_manifest(old_manifest, current) is True
    assert await service.validate_execution_manifest(new_manifest, current) is True
    assert (
        await service.validate_execution_manifest(
            replace(old_manifest, packet_revision=2), current
        )
        is False
    )
    assert (
        await service.validate_execution_manifest(
            replace(old_manifest, canonical_request_hmac="f" * 64), current
        )
        is False
    )
    _, unsent, _, _, _ = await _prepare_result_capture(
        (scope, current, store, registry, clock),
        operation_id="never-sent",
        mark_sending=False,
    )
    assert await service.validate_execution_manifest(unsent, current) is False


@pytest.mark.asyncio
async def test_real_mysql_acked_before_pg_commit_must_not_activate_after_candidate_expiry(
    refresh_case,
):
    from efficiency_platform_agent.persistence.memory_execution import _fingerprint

    scope, _, store, registry, clock = refresh_case

    async def fail_after_mysql_ack(point):
        if point == "after_mysql_settlement":
            assert clock[0] == 161
            raise RuntimeError("RF03_ACKED_BEFORE_PG_FAULT")

    service, wait, command = await _begin_refresh_candidate(
        refresh_case, fault_hook=fail_after_mysql_ack
    )
    with pytest.raises(RuntimeError, match="RF03_ACKED_BEFORE_PG_FAULT"):
        await service.resume(scope.conversation, scope.execution_id, command)
    key = (scope.conversation.tenant_id, scope.execution_id)
    split_pg = await registry._one(
        "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
        key,
    )
    assert split_pg["state"] == "REFRESH_PENDING" and split_pg["refresh_count"] == 1
    assert split_pg["pending_resume_request_id"] == command.resume_request_id
    async with store.engine.connect() as connection:
        split_mysql = (
            (
                await connection.execute(
                    text(
                        "SELECT * FROM agent_memory_context_refresh WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='REFRESH' AND record_id=:candidate"
                    ),
                    {
                        "tenant": key[0].encode(),
                        "execution": key[1].encode(),
                        "candidate": command.resume_request_id.encode(),
                    },
                )
            )
            .mappings()
            .one()
        )
    assert split_mysql["phase"] == "ACKED" and split_mysql["receipt_state"] == "ACTIVE"
    assert split_mysql["refresh_count"] == 1 and split_mysql["expires_at"] == 170
    frozen_mysql = _fingerprint(
        {
            key: bytes(value).hex()
            if isinstance(value, (bytes, bytearray, memoryview))
            else value
            for key, value in split_mysql.items()
        }
    )
    clock[0] = 171
    service.fault_hook = None
    receipt = await service.resume(scope.conversation, scope.execution_id, command)
    after = await registry._one(
        "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
        key,
    )
    assert after["refresh_count"] == 1
    assert (
        after["state"] == "BLOCKED"
        and after["terminal_reason"] == "MEMORY_AUTHORITY_UNAVAILABLE"
    )
    assert after["packet_revision"] == 2 and after["packet_expires_at"] == 170
    assert (
        after["current_context_fingerprint"]
        == split_mysql["target_context_fingerprint"]
    )
    assert all(
        after[key] is None
        for key in (
            "pending_resume_request_id",
            "pending_candidate_digest",
            "pending_packet_revision",
            "pending_context_fingerprint",
        )
    )
    assert all(
        after[key] == split_pg[key]
        for key in (
            "wait_event_id",
            "wait_status",
            "wait_packet_revision",
            "wait_context_fingerprint",
            "wait_phase",
            "original_deadline",
            "execution_revision",
        )
    )
    assert (
        receipt.candidate_phase == "ABORTED"
        and receipt.code == "MEMORY_AUTHORITY_UNAVAILABLE"
    )
    assert receipt.dispatch_allowed is False
    assert receipt.wait_event_id == wait.wait_event_id
    assert (
        await service.resume(scope.conversation, scope.execution_id, command) == receipt
    )
    async with store.engine.connect() as connection:
        unchanged = (
            (
                await connection.execute(
                    text(
                        "SELECT * FROM agent_memory_context_refresh WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='REFRESH' AND record_id=:candidate"
                    ),
                    {
                        "tenant": key[0].encode(),
                        "execution": key[1].encode(),
                        "candidate": command.resume_request_id.encode(),
                    },
                )
            )
            .mappings()
            .one()
        )
        records = (
            await connection.execute(
                text(
                    "SELECT COUNT(*) FROM agent_memory_context_refresh WHERE tenant_id=:tenant AND execution_id=:execution"
                ),
                {"tenant": key[0].encode(), "execution": key[1].encode()},
            )
        ).scalar_one()
    assert (
        _fingerprint(
            {
                key: bytes(value).hex()
                if isinstance(value, (bytes, bytearray, memoryview))
                else value
                for key, value in unchanged.items()
            }
        )
        == frozen_mysql
    )
    assert records == 2
