"""D17真实MySQL安全负例；完整Java→Agent→PG正例由PrivateMemoryLifecycleIntegrationTest驱动。"""
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from efficiency_platform_agent.core.memory_execution import MemoryInvalidation
from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher
from efficiency_platform_agent.persistence.memory_cleanup import (
    MySqlMemoryCleanupJournal,
)
from efficiency_platform_agent.persistence.memory_execution import (
    MySqlMemoryExecutionStore,
)
from tests.integration.context_control.test_memory_execution_mysql import (
    configured_url,
    context,
)

pytestmark = pytest.mark.skipif(os.environ.get("MEMORY_IT_ENABLED") != "1", reason="须root显式本机隔离MySQL+已审SCRUB增量")


@pytest.mark.asyncio
async def test_old_event_receipt_cannot_authorize_scrubbing_a_later_revocation():
    engine = create_async_engine(configured_url())
    store = MySqlMemoryExecutionStore(engine, MemorySnapshotCipher("isolated", {"isolated": os.urandom(32)}))
    original = context()
    tenant, execution = original.packet.scope.tenant_id, original.packet.execution_id
    old, newer = uuid4().hex, uuid4().hex
    params = {"tenant": tenant.encode(), "execution": execution.encode(), "old": old.encode()}
    try:
        await store.claim(original, uuid4().hex, "OPERATIONS", "c" * 64, original.deadline_epoch_seconds)
        await store.invalidate(MemoryInvalidation(tenant, execution, old, original.packet.execution_revision, 1, 2, 1))
        # 故障注入：即使数据库存在上一事件的完整回执字段，也不能证明下一事件已实际停止/清理。
        async with engine.begin() as connection:
            await connection.execute(text("UPDATE agent_memory_invalidation_receipt SET cleanup_fingerprint=:fingerprint,stop_confirmed=TRUE,threads_receipt='old-threads-proof',scrub_receipt='old-snapshot-proof',expected_execution_revision=:revision,grant_epoch=1,source_epoch=2,deletion_epoch=1 WHERE tenant_id=:tenant AND event_id=:old"), params | {"fingerprint": "a" * 64, "revision": original.packet.execution_revision})
        await store.invalidate(MemoryInvalidation(tenant, execution, newer, original.packet.execution_revision, 2, 3, 2))
        with pytest.raises(DBAPIError, match="MEMORY_EXECUTION_SCRUB_PROOF_REQUIRED"):
            async with engine.begin() as connection:
                await connection.execute(text("UPDATE agent_memory_execution SET state='SCRUBBED',snapshot_ciphertext=NULL,snapshot_nonce=NULL,scrub_event_id=:old,scrub_authority=JSON_OBJECT() WHERE tenant_id=:tenant AND execution_id=:execution"), params)
        async with engine.connect() as connection:
            row = (await connection.execute(text("SELECT state,snapshot_ciphertext IS NOT NULL AS has_body,scrub_event_id FROM agent_memory_execution WHERE tenant_id=:tenant AND execution_id=:execution"), params)).mappings().one()
            assert row["state"] == "REVOKED" and row["has_body"] == 1 and row["scrub_event_id"] is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cleanup_persists_raw_to_effective_epoch_mapping_without_relaxing_d13_invalidation():
    engine = create_async_engine(configured_url())
    store = MySqlMemoryExecutionStore(engine, MemorySnapshotCipher("isolated", {"isolated": os.urandom(32)}))
    journal = MySqlMemoryCleanupJournal(engine)
    original = context()
    tenant, execution = original.packet.scope.tenant_id, original.packet.execution_id
    low = MemoryInvalidation(tenant, execution, uuid4().hex, original.packet.execution_revision, 1, 2, 1)
    try:
        await store.claim(original, uuid4().hex, "OPERATIONS", "e" * 64, original.deadline_epoch_seconds)
        await store.invalidate(MemoryInvalidation(tenant, execution, uuid4().hex, original.packet.execution_revision, 3, 4, 3))
        record = await store.get(tenant, execution)
        receipt = await journal.revoke(low, original.packet.safety_dependencies, record)
        await store.invalidate(MemoryInvalidation(tenant, execution, uuid4().hex, original.packet.execution_revision, 5, 6, 5))
        assert await journal.revoke(low, original.packet.safety_dependencies, record) == receipt
        async with engine.connect() as connection:
            row = (await connection.execute(text("SELECT grant_epoch,source_epoch,deletion_epoch,stop_confirmed FROM agent_memory_invalidation_receipt WHERE tenant_id=:tenant AND event_id=:event"), {"tenant": tenant.encode(), "event": low.event_id.encode()})).mappings().one()
            assert (row["grant_epoch"], row["source_epoch"], row["deletion_epoch"]) == (3, 4, 3)
            assert not row["stop_confirmed"]
        with pytest.raises(ValueError, match="MEMORY_INVALIDATION_CONFLICT_409"):
            await store.invalidate(MemoryInvalidation(tenant, execution, uuid4().hex, original.packet.execution_revision, 1, 2, 1))
    finally:
        await engine.dispose()
