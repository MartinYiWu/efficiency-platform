"""局部 ACK 与 PG 全局安装之间的有界安全终结。"""

import asyncio
from dataclasses import replace

import pytest

from efficiency_platform_agent.persistence.mysql_codec import _immutable_object, _plain
from tests.integration.memory.test_refresh_persistence import (
    _begin_refresh_candidate,
)
from tests.integration.memory.test_refresh_persistence import (
    refresh_case as refresh_case,  # noqa: PLC0414
)
from tests.integration.memory.test_refresh_run_metadata import (
    _begin as begin_ops,
)
from tests.integration.memory.test_refresh_run_metadata import (
    ops_case as ops_case,  # noqa: PLC0414
)


async def _pg_row(scope, registry):
    return await registry._one(
        "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
        (scope.conversation.tenant_id, scope.execution_id),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_dispatch", [True, False])
async def test_real_partial_ack_preserves_original_dispatch_and_requires_live_frame(
    refresh_case, initial_dispatch
):
    scope, _, _, registry, _ = refresh_case
    live = [initial_dispatch]

    async def frame(_wait, _runtime):
        return live[0]

    async def update(_old, _new):
        return True

    async def fail(point):
        if point == "after_mysql_settlement":
            raise RuntimeError("LOCAL_ACK_FAULT")

    service, _, command = await _begin_refresh_candidate(
        refresh_case, fault_hook=fail, frame_verifier=frame
    )
    service.binding_updater = update
    with pytest.raises(RuntimeError, match="LOCAL_ACK_FAULT"):
        await service.resume(scope.conversation, scope.execution_id, command)
    assert (await _pg_row(scope, registry))["state"] == "REFRESH_PENDING"
    live[0] = not initial_dispatch
    service.fault_hook = None
    receipt = await service.resume(scope.conversation, scope.execution_id, command)
    assert receipt.dispatch_allowed is False and receipt.refresh_count == 1
    assert receipt.candidate_phase == ("ABORTED" if initial_dispatch else "ACKED")
    row = await _pg_row(scope, registry)
    assert row["state"] == ("BLOCKED" if initial_dispatch else "ACTIVE")
    assert row["packet_revision"] == 2 and row["pending_resume_request_id"] is None
    assert (
        await service.resume(scope.conversation, scope.execution_id, command) == receipt
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("expire_during_frame", [False, True])
async def test_real_new_local_ack_rechecks_ttl_after_last_async_verification(
    refresh_case, expire_during_frame
):
    scope, _, _, registry, clock = refresh_case
    calls = [0]

    async def frame(_wait, _runtime):
        calls[0] += 1
        await asyncio.sleep(0)
        if expire_during_frame and calls[0] == 2:
            clock[0] = 171
        return True

    async def update(_old, _new):
        return True

    async def after_commit(point):
        if point == "after_mysql_settlement" and not expire_during_frame:
            await asyncio.sleep(0)
            clock[0] = 171

    service, _, command = await _begin_refresh_candidate(
        refresh_case, fault_hook=after_commit, frame_verifier=frame
    )
    service.binding_updater = update
    receipt = await service.resume(scope.conversation, scope.execution_id, command)
    assert receipt.candidate_phase == "ABORTED" and receipt.state == "BLOCKED"
    assert receipt.dispatch_allowed is False and receipt.refresh_count == 1
    row = await _pg_row(scope, registry)
    assert row["state"] == "BLOCKED" and row["packet_revision"] == 2
    assert row["packet_expires_at"] == 170


@pytest.mark.asyncio
async def test_real_ops_partial_ack_recovery_rejects_changed_run_anchor(ops_case):
    scope, record, _, registry, _, repository, _, *_ = ops_case

    async def fail(point):
        if point == "after_mysql_settlement":
            raise RuntimeError("LOCAL_ACK_FAULT")

    service, command = await begin_ops(ops_case, fail)
    with pytest.raises(RuntimeError, match="LOCAL_ACK_FAULT"):
        await service.resume(scope.conversation, scope.execution_id, command)
    current = await repository.get(record.runtime_id, scope.conversation.tenant_id)
    metadata = _plain(current.request.metadata)
    metadata["context_request_fingerprint"] = "0" * 64
    await repository.save(
        replace(
            current,
            request=replace(current.request, metadata=_immutable_object(metadata)),
            version=current.version + 1,
        ),
        current.version,
    )
    service.fault_hook = None
    with pytest.raises(ValueError, match="MEMORY_RESUME_CONFLICT"):
        await service.resume(scope.conversation, scope.execution_id, command)
    row = await _pg_row(scope, registry)
    assert row["state"] == "REFRESH_PENDING" and row["refresh_count"] == 1
