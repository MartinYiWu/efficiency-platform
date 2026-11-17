"""仅root本机随机Schema的真实MySQL技术授权验收；不自动建库、不访问模型。"""

import asyncio
import json
import os
import re
from dataclasses import replace
from pathlib import Path
from time import time
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine

from efficiency_platform_agent.contracts.memory import MemoryContextPacketModel
from efficiency_platform_agent.core.memory import MemoryPolicy
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionContext,
    MemoryExecutionGrant,
    MemoryInvalidation,
)
from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher
from efficiency_platform_agent.persistence.memory_execution import (
    MySqlMemoryExecutionStore,
)
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("MEMORY_IT_ENABLED") != "1", reason="需root显式本机隔离MySQL"
)


def configured_url():
    jdbc = os.environ["MEMORY_IT_MYSQL_JDBC_URL"]
    matched = re.fullmatch(
        r"jdbc:mysql://127\.0\.0\.1:(\d+)/(aiep_memory_it_20261117_[0-9a-f]{10})(?:\?.*)?",
        jdbc,
    )
    if matched is None:
        raise ValueError("MEMORY_IT_LOCAL_SCHEMA_REQUIRED")
    return URL.create(
        "mysql+asyncmy",
        username=os.environ["MEMORY_IT_MYSQL_USER"],
        password=os.environ["MEMORY_IT_MYSQL_PASSWORD"],
        host="127.0.0.1",
        port=int(matched[1]),
        database=matched[2],
    )


def context():
    raw = json.loads(
        (Path(__file__).parents[2] / "fixtures/memory_packet_transport.json").read_text(
            encoding="utf-8"
        )
    )["packet"]
    packet = MemoryContextPacketModel.model_validate_json(json.dumps(raw)).to_core()
    packet = replace(
        packet,
        execution_id=uuid4().hex,
        issued_at=int(time()),
        expires_at=int(time()) + 60,
    )
    policy = MemoryPolicy(
        "policy",
        packet.policy_version,
        "operations",
        frozenset({"operations"}),
        readable_layers=frozenset({"semantic"}),
        allowed_scopes=frozenset({"USER_PRIVATE"}),
        field_allowlist=frozenset({"response.language"}),
        source_types=frozenset({"USER_PREFERENCE_DECISION"}),
    )
    return MemoryExecutionContext(
        packet,
        policy,
        (MemoryExecutionGrant("display", "operations", "assistant_response"),),
        int(time()) + 120,
        memory_packet_digest(packet),
        memory_packet_semantic_digest(packet),
        "b" * 64,
    )


@pytest.mark.asyncio
async def test_real_unique_execution_encrypted_restart_and_monotonic_receipt():
    first_engine, second_engine = (
        create_async_engine(configured_url()),
        create_async_engine(configured_url()),
    )
    cipher = MemorySnapshotCipher("isolated-test", {"isolated-test": os.urandom(32)})
    store, competitor = (
        MySqlMemoryExecutionStore(first_engine, cipher),
        MySqlMemoryExecutionStore(second_engine, cipher),
    )
    original = context()
    tenant, execution = original.packet.scope.tenant_id, original.packet.execution_id
    deadline = int(time()) + 90
    try:
        outcomes = await asyncio.gather(
            store.claim(original, uuid4().hex, "OPERATIONS", "a" * 64, deadline),
            competitor.claim(
                original, uuid4().hex, "OPERATIONS", "a" * 64, deadline + 10
            ),
        )
        assert sum(created for _, created in outcomes) == 1
        assert outcomes[0][0] == outcomes[1][0]
        winner = outcomes[0][0]
        async with first_engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT snapshot_ciphertext,snapshot_nonce,key_version FROM agent_memory_execution WHERE tenant_id=:tenant AND execution_id=:execution"
                    ),
                    {"tenant": tenant.encode(), "execution": execution.encode()},
                )
            ).first()
            assert (
                row is not None and b"zh-CN" not in bytes(row[0]) and len(row[1]) == 12
            )
        await first_engine.dispose()
        fresh_engine = create_async_engine(configured_url())
        try:
            restarted = MySqlMemoryExecutionStore(fresh_engine, cipher)
            assert await restarted.get(tenant, execution) == winner
            with pytest.raises(ValueError, match="MEMORY_EXECUTION_CONFLICT_409"):
                await restarted.claim(
                    original, uuid4().hex, "OPERATIONS", "c" * 64, deadline + 1000
                )
            reused, created = await restarted.claim(
                original, uuid4().hex, "OPERATIONS", "a" * 64, deadline + 1000
            )
            assert (
                not created
                and reused.deadline_epoch_seconds == winner.deadline_epoch_seconds
            )
            event = MemoryInvalidation(
                tenant,
                execution,
                uuid4().hex,
                original.packet.execution_revision,
                1,
                2,
                1,
            )
            ack = await restarted.invalidate(event)
            assert await competitor.invalidate(event) == ack
            revoked = await restarted.get(tenant, execution)
            assert revoked.state == "REVOKED"
            with pytest.raises(ValueError, match="MEMORY_INVALIDATION_CONFLICT_409"):
                await restarted.invalidate(replace(event, source_epoch=3))
            with pytest.raises(ValueError, match="MEMORY_INVALIDATION_CONFLICT_409"):
                await restarted.invalidate(
                    replace(event, event_id=uuid4().hex, deletion_epoch=0)
                )
            with pytest.raises(ValueError, match="MEMORY_ACCESS_REVOKED"):
                await restarted.claim(
                    original, uuid4().hex, "OPERATIONS", "a" * 64, deadline + 1000
                )
        finally:
            await fresh_engine.dispose()
    finally:
        await first_engine.dispose()
        await second_engine.dispose()
