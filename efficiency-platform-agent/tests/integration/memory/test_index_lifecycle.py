"""真实索引SQL经临时SQLite连接fixture；不连接PG/供应商。"""

import asyncio
import hashlib
import json
import sqlite3
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from openai import AsyncOpenAI

from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.core.memory import ConversationScope, ExecutionScope
from efficiency_platform_agent.core.memory_index import (
    IndexDelete,
    IndexUpsert,
    MemoryIndexIdentity,
    MemoryIndexScope,
    MemoryIndexSpace,
)
from efficiency_platform_agent.core.paid_budget import PaidBudgetPlan, PaidPriceLimit
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    bind_run_context,
)
from efficiency_platform_agent.harness.memory_index_runtime import (
    MemoryIndexCleanupRuntime,
)
from efficiency_platform_agent.memory.indexing import (
    GuardedMemoryIndexEmbedding,
    MemoryIndexingService,
)
from efficiency_platform_agent.memory.recall import AuthorizedMemoryRecall
from efficiency_platform_agent.persistence.memory_index import PostgresMemoryIndex
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.providers.database.postgres import PostgresProvider
from efficiency_platform_agent.providers.embedding.dashscope import (
    DashScopeEmbeddingProvider,
)
from efficiency_platform_agent.providers.paid_http import PaidHttpTransport


class SqliteConnection:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS memory_index_fences(scope_key TEXT,item_id TEXT,generation INTEGER,deletion_epoch INTEGER,deleted BOOLEAN,forget_epoch INTEGER NOT NULL DEFAULT -1,PRIMARY KEY(scope_key,item_id));
        CREATE TABLE IF NOT EXISTS memory_query_operations(tenant_id TEXT,task_id TEXT,scope_key TEXT,embedding_model TEXT,dimension INTEGER,policy_version TEXT,query_hash TEXT,fingerprint TEXT,token TEXT UNIQUE,state TEXT,operation_id TEXT,embedding TEXT,item_refs TEXT,created_at INTEGER,expires_at INTEGER NOT NULL,PRIMARY KEY(tenant_id,task_id));
        CREATE TABLE IF NOT EXISTS memory_index_task_slots(tenant_id TEXT,task_id TEXT,operation_id TEXT UNIQUE,fingerprint TEXT,PRIMARY KEY(tenant_id,task_id));
        CREATE TABLE IF NOT EXISTS memory_index_jobs(scope_key TEXT,embedding_model TEXT,dimension INTEGER,policy_version TEXT,item_id TEXT,generation INTEGER,version_id TEXT,deletion_epoch INTEGER,source_fingerprint TEXT,fingerprint TEXT,token TEXT UNIQUE,state TEXT,operation_id TEXT,event_id TEXT,created_at INTEGER,PRIMARY KEY(scope_key,embedding_model,dimension,policy_version,item_id,generation));
        CREATE TABLE IF NOT EXISTS memory_index_entries(scope_key TEXT,embedding_model TEXT,dimension INTEGER,policy_version TEXT,item_id TEXT,generation INTEGER,version_id TEXT,deletion_epoch INTEGER,source_fingerprint TEXT,embedding TEXT,terms TEXT,expires_at INTEGER NOT NULL,PRIMARY KEY(scope_key,embedding_model,dimension,policy_version,item_id));
        """)

    async def execute(self, sql, params=()):
        sql = (
            sql.replace("agent_runtime.", "")
            .replace("%s", "?")
            .replace(" FOR UPDATE", "")
            .replace(" SKIP LOCKED", "")
        )
        return self.db.execute(sql, params)

    @asynccontextmanager
    async def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise


def request():
    conversation = ConversationScope(
        "tenant", "user", "operations", "operations", "TASK_ONLY", None
    )
    return IndexUpsert(
        "event",
        MemoryIndexScope("tenant", "user", "operations", "operations"),
        MemoryIndexSpace("model", 2, "policy"),
        MemoryIndexIdentity("item", "version", 1, 0, "a" * 64),
        ExecutionScope(
            conversation, "task", "run", "index", "memory.index", "operations"
        ),
        int(time.time()) + 60,
        "approved redacted projection",
        ("language", "zh"),
    )


class Authority:
    def __init__(self):
        self.checked = 0

    async def check_upsert(self, value):
        self.checked += 1

    async def check_delete(self, value):
        self.checked += 1


class Embedding:
    def __init__(self):
        self.calls = 0
        self.fail = False

    async def embed_index(self, lease):
        self.calls += 1
        if self.fail:
            raise RuntimeError("fixture interrupted")
        return (1.0, 0.0)


def build(path, embedding):
    connection = SqliteConnection(path)
    index = PostgresMemoryIndex(
        PostgresProvider(connection, "agent_runtime", allow_runtime_schema=True)
    )
    return index, MemoryIndexingService(
        index, Authority(), embedding, enabled=True, fixture=True
    )


async def test_durable_duplicate_delete_and_filtered_exact_refs(tmp_path):
    embedding = Embedding()
    path = tmp_path / "index.sqlite3"
    index, service = build(path, embedding)
    value = request()
    assert await service.upsert(value) == "READY"
    assert await service.upsert(replace(value, event_id="another-event")) == "READY"
    assert embedding.calls == 1
    index, service = build(path, embedding)
    assert await service.upsert(value) == "READY"
    assert embedding.calls == 1
    vector, lexical = await index.search(
        value.scope,
        value.space,
        (value.identity,),
        vector=(1.0, 0.0),
        terms=("zh",),
        limit=30,
    )
    assert vector[0].identity == lexical[0].identity == value.identity
    assert await index.search(
        replace(value.scope, user_id="other"),
        value.space,
        (value.identity,),
        vector=(1.0, 0.0),
        terms=("zh",),
        limit=30,
    ) == ((), ())
    stored = index.provider.connection.db.execute(
        "SELECT embedding,terms FROM memory_index_entries"
    ).fetchone()
    assert value.projection not in json.dumps(stored)
    await service.delete(IndexDelete("delete", value.scope, "item", 1, 1))
    with pytest.raises(ValueError, match="STALE_OR_DELETED"):
        await service.upsert(replace(value, event_id="late-event"))
    assert await index.search(
        value.scope,
        value.space,
        (value.identity,),
        vector=(1.0, 0.0),
        terms=("zh",),
        limit=30,
    ) == ((), ())
    assert embedding.calls == 1


async def test_generation_and_unknown_never_reembed_after_restart(tmp_path):
    path = tmp_path / "index.sqlite3"
    embedding = Embedding()
    index, service = build(path, embedding)
    value = request()
    embedding.fail = True
    with pytest.raises(RuntimeError):
        await service.upsert(value)
    index, service = build(path, embedding)
    with pytest.raises(ValueError, match="OPERATION_UNRESOLVED"):
        await service.upsert(replace(value, event_id="replay"))
    assert embedding.calls == 1
    assert len(await index.pending_operations(now=int(time.time()) + 86401)) == 1
    await service.delete(IndexDelete("delete", value.scope, "item", 2, 2))
    newer = replace(
        value,
        identity=replace(value.identity, generation=3, deletion_epoch=3),
        execution=replace(value.execution, task_id="task-new"),
    )
    embedding.fail = False
    assert await service.upsert(newer) == "READY"
    with pytest.raises(ValueError, match="STALE_OR_DELETED"):
        await service.upsert(value)
    assert embedding.calls == 2


async def test_bad_dimension_default_off_and_task_slot(tmp_path):
    index, service = build(tmp_path / "index.sqlite3", Embedding())
    value = request()
    lease = await index.claim(value)
    with pytest.raises(ValueError, match="VECTOR_INVALID"):
        await index.complete(lease, (1.0,))
    second = replace(value, identity=replace(value.identity, item_id="other"))
    with pytest.raises(ValueError, match="TASK_OPPORTUNITY_USED"):
        await index.claim(second)
    service.enabled = False
    with pytest.raises(ValueError, match="FEATURE_DISABLED"):
        await service.upsert(value)
    await index.delete(IndexDelete("delete-first", value.scope, "late-item", 2, 1))
    late = replace(
        value,
        identity=replace(value.identity, item_id="late-item", generation=2),
        execution=replace(value.execution, task_id="late-task"),
    )
    with pytest.raises(ValueError, match="STALE_OR_DELETED"):
        await index.claim(late)


async def test_retention_outlives_send_window_and_same_generation_cannot_extend(
    tmp_path, monkeypatch
):
    index, service = build(tmp_path / "retention.sqlite3", Embedding())
    now = int(time.time())
    value = replace(request(), expires_at=now + 60, retention_expires_at=now + 3600)
    assert await service.upsert(value) == "READY"
    with pytest.raises(ValueError, match="GENERATION_CONFLICT"):
        await service.upsert(
            replace(value, event_id="extend", retention_expires_at=now + 7200)
        )
    monkeypatch.setattr(time, "time", lambda: now + 100)
    vector, lexical = await index.search(
        value.scope,
        value.space,
        (value.identity,),
        vector=(1.0, 0.0),
        terms=("zh",),
        limit=30,
    )
    assert vector and lexical
    with pytest.raises(ValueError, match="AUTHORIZATION_EXPIRED"):
        await service.upsert(replace(value, event_id="old-window"))
    monkeypatch.setattr(time, "time", lambda: now + 3601)
    assert await index.search(
        value.scope,
        value.space,
        (value.identity,),
        vector=(1.0, 0.0),
        terms=("zh",),
        limit=30,
    ) == ((), ())


async def test_query_unknown_and_task_quota_survive_new_execution(tmp_path):
    path = tmp_path / "query.sqlite3"
    index, _ = build(path, Embedding())
    value = request()
    authorization = AuthorizedMemoryRecall(
        value.scope,
        value.space,
        value.execution,
        (value.identity,),
        value.expires_at,
        True,
    )
    query = "never persist this query text"
    digest = hashlib.sha256(query.encode()).hexdigest()
    lease = await index.claim_query(authorization, digest)
    await index.fail_query_unknown(lease)
    index, _ = build(path, Embedding())
    successor = replace(
        authorization, execution=replace(value.execution, execution_id="new-run")
    )
    with pytest.raises(ValueError, match="OPERATION_UNRESOLVED"):
        await index.claim_query(successor, digest, preview=True)
    with pytest.raises(ValueError, match="TASK_OPPORTUNITY_USED"):
        await index.claim_query(successor, hashlib.sha256(b"other").hexdigest())
    persisted = index.provider.connection.db.execute(
        "SELECT * FROM memory_query_operations"
    ).fetchone()
    assert query not in json.dumps(persisted)


async def test_expiry_worker_physically_erases_all_scopes_and_keeps_unknown_slots(
    tmp_path, monkeypatch
):
    index, service = build(tmp_path / "expiry.sqlite3", Embedding())
    now = int(time.time())
    first = replace(request(), expires_at=now + 30, retention_expires_at=now + 60)
    second = replace(
        first,
        scope=replace(first.scope, user_id="other-user"),
        execution=replace(
            first.execution,
            conversation=replace(first.execution.conversation, user_id="other-user"),
            task_id="other-task",
        ),
    )
    await service.upsert(first)
    await service.upsert(second)
    authorizations = [
        AuthorizedMemoryRecall(
            value.scope, value.space, value.execution, (value.identity,), now + 40, True
        )
        for value in (first, second)
    ]
    first_lease = await index.claim_query(
        authorizations[0],
        "a" * 64,
        expires_at=await index.query_retention(authorizations[0]),
    )
    await index.complete_query(first_lease, (1.0, 0.0), first.space)
    unknown = await index.claim_query(
        authorizations[1],
        "b" * 64,
        expires_at=await index.query_retention(authorizations[1]),
    )
    await index.fail_query_unknown(unknown)
    limited = await index.expire(None, now=now + 61, limit=1)
    assert (
        len(limited["index_receipts"]) == 1
        and limited["query_scrubbed"] == 1
        and limited["remaining"]
    )
    monkeypatch.setattr(time, "time", lambda: now + 61)
    cleanup = MemoryIndexCleanupRuntime(index)
    await cleanup.expiry_worker.start()
    try:
        await asyncio.wait_for(cleanup.expiry_worker.completed.wait(), 2)
        assert not cleanup.expiry_worker.last_error
    finally:
        await cleanup.expiry_worker.close()
    db = index.provider.connection.db
    assert db.execute("SELECT COUNT(*) FROM memory_index_entries").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM memory_index_task_slots").fetchone()[0] == 2
    assert (
        db.execute(
            "SELECT COUNT(*) FROM memory_index_jobs WHERE state='DELETED'"
        ).fetchone()[0]
        == 2
    )
    rows = db.execute(
        "SELECT state,embedding,item_refs,fingerprint FROM memory_query_operations ORDER BY task_id"
    ).fetchall()
    assert {row[0] for row in rows} == {"DELETED", "UNKNOWN"}
    assert all(row[1] is None and row[2] == "[]" and len(row[3]) == 64 for row in rows)
    assert (
        db.execute(
            "SELECT COUNT(*) FROM memory_index_fences WHERE deleted=TRUE"
        ).fetchone()[0]
        == 2
    )
    with pytest.raises(ValueError, match="STALE_OR_DELETED"):
        await index.claim(
            replace(
                first,
                expires_at=now + 120,
                retention_expires_at=now + 180,
                execution=replace(first.execution, task_id="late-task"),
            )
        )


async def test_expired_ready_query_scrubs_before_reject_and_never_reembeds(
    tmp_path, monkeypatch
):
    index, service = build(tmp_path / "query-expiry.sqlite3", Embedding())
    now = int(time.time())
    value = replace(request(), expires_at=now + 30, retention_expires_at=now + 3600)
    await service.upsert(value)
    authorization = AuthorizedMemoryRecall(
        value.scope, value.space, value.execution, (value.identity,), now + 20, True
    )
    deadline = await index.query_retention(authorization)
    assert deadline == now + 20
    lease = await index.claim_query(authorization, "c" * 64, expires_at=deadline)
    await index.complete_query(lease, (1.0, 0.0), value.space)
    monkeypatch.setattr(time, "time", lambda: now + 21)
    successor = replace(
        authorization,
        expires_at=now + 100,
        execution=replace(value.execution, execution_id="new-run"),
    )
    with pytest.raises(ValueError, match="RETENTION_EXPIRED"):
        await index.claim_query(successor, "c" * 64, preview=True)
    row = index.provider.connection.db.execute(
        "SELECT state,embedding,item_refs,query_hash FROM memory_query_operations"
    ).fetchone()
    assert row == ("DELETED", None, "[]", "c" * 64)
    assert (
        index.provider.connection.db.execute(
            "SELECT COUNT(*) FROM memory_query_operations"
        ).fetchone()[0]
        == 1
    )


async def test_late_correction_delete_preserves_new_generation_and_future_upsert(
    tmp_path,
):
    index, service = build(tmp_path / "ordered.sqlite3", Embedding())
    value = request()
    assert await service.upsert(value) == "READY"
    newer = replace(
        value,
        identity=replace(value.identity, generation=2, version_id="v2"),
        execution=replace(value.execution, task_id="task2"),
    )
    assert await service.upsert(newer) == "READY"
    await service.delete(
        IndexDelete("late-old", value.scope, value.identity.item_id, 1, 0)
    )
    assert (
        await index.search(
            value.scope,
            value.space,
            (newer.identity,),
            vector=(1.0, 0.0),
            terms=("zh",),
            limit=30,
        )
    )[0]
    await service.delete(
        IndexDelete("correction", value.scope, value.identity.item_id, 2, 0)
    )
    future = replace(
        newer,
        identity=replace(newer.identity, generation=3, version_id="v3"),
        execution=replace(value.execution, task_id="task3"),
    )
    assert await service.upsert(future) == "READY"
    await service.delete(
        IndexDelete("forget", value.scope, value.identity.item_id, 1, 1)
    )
    with pytest.raises(ValueError, match="STALE_OR_DELETED"):
        await service.upsert(
            replace(
                future,
                identity=replace(future.identity, generation=4, deletion_epoch=1),
                execution=replace(value.execution, task_id="task4"),
            )
        )
    assert await index.search(
        value.scope,
        value.space,
        (future.identity,),
        vector=(1.0, 0.0),
        terms=("zh",),
        limit=30,
    ) == ((), ())


async def test_guarded_embedding_uses_original_task_paid_transport_once(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("EFFICIENCY_TASK_AUTHORIZATION_ENABLED", "true")
    value = replace(
        request(), space=MemoryIndexSpace("text-embedding-v4", 1024, "policy")
    )
    ledger = SqlitePaidBudgetLedger(
        tmp_path / "paid.sqlite3", task_authorization_enabled=True
    )
    ledger.initialize_task_authorization_schema(tmp_path / "paid-before.sqlite3")
    ledger.authorize(
        PaidBudgetPlan(
            "budget",
            3,
            300,
            int(time.time() * 1000) + 60000,
            3,
            300,
            60000,
            1,
            2,
            100000,
            0,
            0,
            100000,
            0,
            0,
        ),
        (
            PaidPriceLimit(
                "embedding",
                "text-embedding-v4",
                10000,
                0,
                100,
                "fixture",
                "v1",
                20000,
                1,
                0,
                0,
            ),
        ),
    )
    ledger.bind_execution(
        "tenant", "run", 60000, context_scope=value.execution.conversation
    )
    sent = []

    async def wire(req):
        sent.append(req)
        return httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [1.0] + [0.0] * 1023}],
                "usage": {"input_tokens": 1},
            },
            request=req,
        )

    transport = PaidHttpTransport(
        ledger,
        httpx.MockTransport(wire),
        "embedding",
        allowed_url="https://fixture.invalid/embeddings",
        require_context_guard=True,
    )
    client = AsyncOpenAI(
        api_key="fixture-not-secret",
        base_url="https://fixture.invalid",
        max_retries=0,
        http_client=httpx.AsyncClient(
            transport=transport, trust_env=False, follow_redirects=False
        ),
    )
    authority = Authority()
    embedding = GuardedMemoryIndexEmbedding(
        DashScopeEmbeddingProvider(client), ledger, authority
    )
    index, _ = build(tmp_path / "index.sqlite3", Embedding())
    service = MemoryIndexingService(index, authority, embedding, enabled=True)
    binding = RunContextBinding(
        value.execution.conversation, "task", "run", value.expires_at
    )
    try:
        with bind_run_context(binding), execution_scope(RunControl()):
            assert await service.upsert(value) == "READY"
            assert await service.upsert(replace(value, event_id="replayed")) == "READY"
        assert len(sent) == 1
        assert ledger.task_authorization_snapshot("task")["calls"] == 1
        assert authority.checked >= 5
    finally:
        await client.close()
