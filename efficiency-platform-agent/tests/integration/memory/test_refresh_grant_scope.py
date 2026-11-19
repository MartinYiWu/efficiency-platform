"""NONE 多授权等待的真实双库边界；原帧核验为显式服务端端口。"""

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import text

from efficiency_platform_agent.contracts.context_control import ContextManifestModel
from efficiency_platform_agent.core.context_control import (
    ContextManifest,
    TokenMeasurement,
    WindowDecision,
)
from efficiency_platform_agent.core.context_ports import ContextOperation
from efficiency_platform_agent.core.memory_execution import MemoryExecutionGrant
from efficiency_platform_agent.core.memory_refresh import (
    MemoryContextResume,
    ResumeMode,
    WaitPhase,
)
from efficiency_platform_agent.memory.context_refresh import MemoryContextRefreshService
from efficiency_platform_agent.persistence.context_manifest import (
    MySqlContextManifestStore,
)
from efficiency_platform_agent.persistence.memory_context_refresh import (
    MySqlMemoryContextRefreshStore,
)
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)
from tests.integration.memory.test_refresh_persistence import (
    refresh_case as refresh_case,  # noqa: PLC0414
)


@pytest.fixture
async def grant_case(refresh_case):
    old_scope, old_record, store, registry, clock = refresh_case
    packet = replace(old_record.context.packet, execution_id=uuid4().hex)
    context = replace(
        old_record.context,
        packet=packet,
        execution_grants=(
            MemoryExecutionGrant(
                "customer-service:answer_general",
                "customer-service",
                "assistant_response",
            ),
            MemoryExecutionGrant(
                "customer-service:intent", "customer-service", "assistant_response"
            ),
        ),
        packet_digest=memory_packet_digest(packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(packet),
    )
    anchor = replace(
        old_scope,
        execution_id=packet.execution_id,
        subtask_id="customer-service:answer_general",
    )
    intent = replace(anchor, subtask_id="customer-service:intent")
    record, _ = await store.claim(
        context, uuid4().hex, "CUSTOMER_SERVICE", "c" * 64, 200
    )
    clock[0] = 150
    await registry.enroll_no_checkpoint(anchor, record.runtime_id)
    clock[0] = 161
    manifests = MySqlContextManifestStore(store.engine, memory_execution_store=store)

    async def prepare(scope):
        operation = ContextOperation(uuid4().hex, 1, 200, False)
        manifest = ContextManifest(
            uuid4().hex,
            scope,
            operation.operation_id,
            scope.subtask_id,
            1,
            "offline/1",
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
            "d" * 64,
        )
        await manifests.save_manifest_once(manifest, operation)
        return manifest, operation

    async def frame(wait, runtime):
        return runtime == record.runtime_id and wait.execution_id == anchor.execution_id

    service = MemoryContextRefreshService(
        registry, MySqlMemoryContextRefreshStore(store), frame_verifier=frame
    )
    return anchor, intent, record, store, registry, service, prepare


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", [WaitPhase.PREPARED, WaitPhase.RESERVED])
async def test_real_none_intent_wait_uses_frozen_grant_and_exact_manifest(
    grant_case, phase
):
    anchor, intent, record, store, registry, service, prepare = grant_case
    manifest, operation = await prepare(intent)
    original = await registry._one(
        "SELECT scope FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
        (anchor.conversation.tenant_id, anchor.execution_id),
    )
    wait_id = await service.begin_wait_intent(
        intent,
        record.runtime_id,
        operation.operation_id,
        1,
        phase,
        canonical_request_hmac=manifest.canonical_request_hmac,
    )
    await service.finish_wait(anchor.conversation, anchor.execution_id, wait_id)
    wait = await service.get_wait(anchor.conversation, anchor.execution_id)
    assert (
        wait.logical_operation_id == operation.operation_id and wait.wait_phase == phase
    )
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
        operation.operation_id,
        manifest.canonical_request_hmac,
        1,
        wait.expected_current_context_fingerprint,
        replace(
            record.context, packet=packet, packet_digest=memory_packet_digest(packet)
        ),
    )
    service.frame_verifier = None
    receipt = await service.resume(anchor.conversation, anchor.execution_id, command)
    assert receipt.code == "CONTEXT_REFRESHED" and receipt.dispatch_allowed is False
    assert receipt.refresh_count == 1
    after = await registry._one(
        "SELECT scope FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
        (anchor.conversation.tenant_id, anchor.execution_id),
    )
    assert after == original
    assert (
        await store.get(anchor.conversation.tenant_id, anchor.execution_id)
    ).context == command.refreshed_context


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        "ungranted_node",
        "wrong_purpose",
        "wrong_agent",
        "wrong_task",
        "wrong_execution",
        "wrong_domain",
        "wrong_manifest",
        "before_prepare",
    ],
)
async def test_real_none_grant_wait_rejects_identity_or_manifest_changes_without_wait(
    grant_case, bad
):
    anchor, intent, record, store, registry, service, prepare = grant_case
    incoming = intent
    if bad == "ungranted_node":
        incoming = replace(intent, subtask_id="customer-service:not-granted")
    if bad == "wrong_purpose":
        incoming = replace(intent, purpose="not-granted")
    if bad == "wrong_agent":
        incoming = replace(intent, execution_agent_id="not-granted")
    if bad == "wrong_task":
        incoming = replace(intent, task_id=uuid4().hex)
    if bad == "wrong_execution":
        incoming = replace(intent, execution_id=uuid4().hex)
    if bad == "wrong_domain":
        incoming = replace(
            intent,
            conversation=replace(
                intent.conversation,
                domain="operations",
                top_level_agent_id="operations",
            ),
        )
    manifest, operation = await prepare(anchor if bad == "wrong_manifest" else incoming)
    phase = WaitPhase.BEFORE_PREPARE if bad == "before_prepare" else WaitPhase.PREPARED
    with pytest.raises((PermissionError, ValueError)):
        await service.begin_wait_intent(
            incoming,
            record.runtime_id,
            operation.operation_id,
            1,
            phase,
            canonical_request_hmac=None
            if phase == WaitPhase.BEFORE_PREPARE
            else manifest.canonical_request_hmac,
        )
    row = await registry._one(
        "SELECT state,refresh_count,wait_event_id FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
        (anchor.conversation.tenant_id, anchor.execution_id),
    )
    assert (
        row["state"] == "ACTIVE"
        and row["refresh_count"] == 0
        and row["wait_event_id"] is None
    )
    async with store.engine.connect() as connection:
        count = (
            await connection.execute(
                text(
                    "SELECT COUNT(*) FROM agent_memory_context_refresh WHERE tenant_id=:tenant AND execution_id=:execution"
                ),
                {
                    "tenant": anchor.conversation.tenant_id.encode(),
                    "execution": anchor.execution_id.encode(),
                },
            )
        ).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_real_grant_wait_historical_refs_allow_original_sent_manifest(grant_case):
    anchor, intent, record, store, _, service, prepare = grant_case
    manifest, operation = await prepare(intent)
    wait_id = await service.begin_wait_intent(
        intent,
        record.runtime_id,
        operation.operation_id,
        1,
        WaitPhase.PREPARED,
        canonical_request_hmac=manifest.canonical_request_hmac,
    )
    await service.finish_wait(anchor.conversation, anchor.execution_id, wait_id)
    original = await service.get_wait(anchor.conversation, anchor.execution_id, wait_id)
    manifests = MySqlContextManifestStore(store.engine, memory_execution_store=store)
    assert await manifests.mark_sending(manifest, operation)
    assert (
        await service.get_wait(anchor.conversation, anchor.execution_id, wait_id)
        == original
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_field", ["scope", "node"])
async def test_real_grant_wait_frozen_manifest_rejects_later_scope_or_node_change(
    grant_case, changed_field
):
    anchor, intent, record, store, registry, service, prepare = grant_case
    manifest, operation = await prepare(intent)
    wait_id = await service.begin_wait_intent(
        intent,
        record.runtime_id,
        operation.operation_id,
        1,
        WaitPhase.PREPARED,
        canonical_request_hmac=manifest.canonical_request_hmac,
    )
    changed = (
        replace(manifest, scope=anchor)
        if changed_field == "scope"
        else replace(manifest, node_id=anchor.subtask_id)
    )
    async with store.engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE agent_context_manifest SET metadata_json=:metadata WHERE tenant_id=:tenant AND task_id=:task AND execution_id=:execution AND operation_id=:operation AND attempt=1"
            ),
            {
                "metadata": ContextManifestModel.from_core(changed).model_dump_json(),
                "tenant": anchor.conversation.tenant_id.encode(),
                "task": anchor.task_id.encode(),
                "execution": anchor.execution_id.encode(),
                "operation": operation.operation_id.encode(),
            },
        )
    with pytest.raises((ValueError, PermissionError)):
        await service.finish_wait(anchor.conversation, anchor.execution_id, wait_id)
    row = await registry._one(
        "SELECT state,refresh_count,wait_status FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
        (anchor.conversation.tenant_id, anchor.execution_id),
    )
    assert (
        row["state"] == "WAITING_CONTEXT"
        and row["wait_status"] == "BUILDING"
        and row["refresh_count"] == 0
    )
    assert (
        await service.get_wait(anchor.conversation, anchor.execution_id, wait_id)
        is None
    )
