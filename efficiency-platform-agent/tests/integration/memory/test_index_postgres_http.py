"""单条原生PG索引纵切；仅root显式启动的本机隔离PG，外部HTTP始终Mock。"""

import hashlib
import os
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from openai import AsyncOpenAI
from psycopg import AsyncConnection, sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from efficiency_platform_agent.api.memory_index_routes import build_memory_index_router
from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.core.memory import (
    ConversationScope,
    ExecutionScope,
    MemoryReference,
    SourceDependency,
)
from efficiency_platform_agent.core.memory_index import (
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
    MemoryIndexRuntime,
    source_fingerprint,
)
from efficiency_platform_agent.persistence.memory_index import PostgresMemoryIndex
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.providers.database.postgres import PostgresProvider
from efficiency_platform_agent.providers.embedding.dashscope import (
    DashScopeEmbeddingProvider,
)
from efficiency_platform_agent.providers.paid_http import PaidHttpTransport

ASSET_HASHES = {
    "00-变更说明.md": "5560b143f6f1a16c2e8d471e5e190ddc235937667498c630bb5b8d132376ec81",
    "01-precheck.sql": "288833ef2b3c62ef5ae485ac7f3eb924447d0b04363fb026136e1799bb69b6f1",
    "02-up.sql": "2e9f9c61c64efb5fd0247bd4ddfdc729389192e24892a7ed0deaa6843a7f6c65",
    "03-verify.sql": "60b30ae8ecb6c3cb88b65d15f95c2dd78ff9691f39b22575ce1dcf4c5d0e3f6d",
    "04-rollback.sql": "3121b51acb5d4c8040e2ef2a7d09ed41215ffa6b57c35ed650a6c4527743d7a8",
}


@pytest.fixture
async def native_index():
    dsn = os.environ.get("MEMORY_IT_POSTGRES_DSN")
    if not dsn or os.environ.get("MEMORY_IT_ALLOW_SCHEMA_DDL") != "1":
        pytest.skip("explicit task-owned local PostgreSQL required")
    if conninfo_to_dict(dsn).get("host") not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("task-owned local PostgreSQL required", pytrace=False)
    assets = Path(__file__).resolve().parents[3] / "sql/bootstrap/memory_index_v1"
    bodies = {}
    for name, expected in ASSET_HASHES.items():
        raw = (assets / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            pytest.fail("reviewed memory_index_v1 asset hash changed", pytrace=False)
        if name.endswith(".sql"):
            bodies[name] = raw.decode("utf-8-sig")
    schema = "agent_runtime_" + secrets.token_hex(4)
    connection = await AsyncConnection.connect(
        dsn,
        autocommit=True,
        prepare_threshold=0,
        row_factory=tuple_row,
        connect_timeout=5,
    )
    created = installed = reverted = False
    try:
        await connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
        )
        created = True
        await connection.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
        )
        await connection.execute(bodies["01-precheck.sql"], prepare=False)
        await connection.execute(bodies["02-up.sql"], prepare=False)
        installed = True
        index = PostgresMemoryIndex(
            PostgresProvider(connection, schema, allow_runtime_schema=True)
        )
        yield index
        await connection.execute(bodies["03-verify.sql"], prepare=False)
        before = (
            await (
                await connection.execute(
                    f"SELECT COUNT(*) FROM {schema}.memory_index_task_slots"
                )
            ).fetchone()
        )[0]
        await connection.execute(bodies["04-rollback.sql"], prepare=False)
        reverted = True
        assert (
            await (
                await connection.execute(
                    f"SELECT COUNT(*) FROM {schema}.memory_index_entries"
                )
            ).fetchone()
        )[0] == 0
        assert (
            await (
                await connection.execute(
                    f"SELECT COUNT(*) FROM {schema}.memory_index_task_slots"
                )
            ).fetchone()
        )[0] == before
    finally:
        try:
            if connection.info.transaction_status != TransactionStatus.IDLE:
                await connection.rollback()
            if installed and not reverted:
                await connection.execute(bodies["04-rollback.sql"], prepare=False)
        finally:
            try:
                if created:
                    await connection.execute(
                        sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
                    )
            finally:
                await connection.close()


async def test_native_postgres_index_http_vertical(native_index, tmp_path, monkeypatch):
    monkeypatch.setenv("EFFICIENCY_TASK_AUTHORIZATION_ENABLED", "true")
    index = native_index
    now = int(time.time())
    conversation = ConversationScope(
        "tenant-native",
        "user-native",
        "operations",
        "operations",
        "CONVERSATION",
        "session-native",
    )
    dependency = SourceDependency("MESSAGE", "source-native", "1", 0, 0, 0)
    scope = MemoryIndexScope("tenant-native", "user-native", "operations", "operations")
    space = MemoryIndexSpace("text-embedding-v4", 1024, "policy-native")
    identity = MemoryIndexIdentity(
        "item-native", "version-1", 1, 0, source_fingerprint((dependency,))
    )
    value = IndexUpsert(
        "event-native",
        scope,
        space,
        identity,
        ExecutionScope(
            conversation, "task-1", "run-1", "index", "memory.index", "operations"
        ),
        now + 60,
        "Please use Chinese.",
        ("Chinese",),
        now + 3600,
    )
    records = {}
    locks = []

    class Store:
        async def get(self, tenant, execution):
            return records.get((tenant, execution))

    class SourceAuthority:
        async def current(self, *args):
            return True

    class Engine:
        @asynccontextmanager
        async def begin(self):
            assert locks == ["pg"]
            locks.append("mysql")
            try:
                yield self
            finally:
                locks.pop()

        async def execute(self, *args):
            return SimpleNamespace(first=lambda: ("ACTIVE",))

    class SendAuthority:
        registry = SimpleNamespace(source_authority=SourceAuthority())
        execution_store = SimpleNamespace(engine=Engine())

        @asynccontextmanager
        async def acquire(self):
            locks.append("pg")
            try:
                yield
            finally:
                locks.pop()

    ledger = SqlitePaidBudgetLedger(
        tmp_path / "fake-paid.sqlite3", task_authorization_enabled=True
    )
    ledger.initialize_task_authorization_schema(tmp_path / "fake-paid-before.sqlite3")
    plan = PaidBudgetPlan(
        "budget-1",
        10,
        1000,
        (now + 600) * 1000,
        10,
        1000,
        600000,
        1,
        2,
        1000000,
        0,
        0,
        1000000,
        0,
        0,
    )
    prices = (
        PaidPriceLimit(
            "embedding",
            space.embedding_model,
            10000,
            0,
            100,
            "fixture-only",
            "v1",
            20000,
            1,
            0,
            0,
        ),
    )
    ledger.authorize(plan, prices)
    sent = []

    async def wire(request):
        assert locks == ["pg", "mysql"]
        sent.append(True)
        return httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [1.0] + [0.0] * 1023}],
                "usage": {"input_tokens": 1},
            },
            request=request,
        )

    async def authorize(request):
        if request.headers.get("Authorization") != "Bearer native-fixture":
            raise PermissionError
        return scope.tenant_id

    @asynccontextmanager
    async def api_frame(request_value):
        packet = SimpleNamespace(
            scope=conversation,
            task_id=request_value.execution.task_id,
            execution_id=request_value.execution.execution_id,
            expires_at=now + 600,
            items=(
                MemoryReference(
                    identity.item_id,
                    request_value.identity.version_id,
                    "response.language",
                    request_value.projection,
                    (dependency,),
                ),
            ),
        )
        context = SimpleNamespace(
            packet=packet,
            policy=SimpleNamespace(version=space.policy_version, max_paid_operations=1),
            deadline_epoch_seconds=now + 600,
            execution_grants=(
                SimpleNamespace(
                    node_id="index",
                    execution_agent_id="operations",
                    purpose="memory.index",
                ),
            ),
        )
        records[(scope.tenant_id, request_value.execution.execution_id)] = (
            SimpleNamespace(
                context=context, state="ACTIVE", deadline_epoch_seconds=now + 600
            )
        )
        transport = PaidHttpTransport(
            ledger,
            httpx.MockTransport(wire),
            "embedding",
            allowed_url="https://native-fixture.invalid/embeddings",
            require_context_guard=True,
        )
        client = AsyncOpenAI(
            api_key="native-fixture-not-secret",
            base_url="https://native-fixture.invalid",
            max_retries=0,
            http_client=httpx.AsyncClient(
                transport=transport, trust_env=False, follow_redirects=False
            ),
        )
        runtime = MemoryIndexRuntime(
            index,
            Store(),
            SendAuthority(),
            ledger,
            DashScopeEmbeddingProvider(client),
            index_enabled=True,
            recall_enabled=True,
            query_embedding_enabled=True,
        )
        app = FastAPI()
        app.include_router(build_memory_index_router(runtime, authorize))
        control = RunControl()
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://native-fixture"
            ) as api:
                with (
                    bind_run_context(
                        RunContextBinding(
                            conversation,
                            request_value.execution.task_id,
                            request_value.execution.execution_id,
                            now + 600,
                            context,
                        )
                    ),
                    execution_scope(control),
                    runtime.for_run(),
                ):
                    yield api
        finally:
            await control.close()
            await client.close()

    headers = {"Authorization": "Bearer native-fixture", "X-Tenant-ID": scope.tenant_id}
    async with api_frame(value) as api:
        for event in (value.event_id, value.event_id, "replayed-native-event"):
            response = await api.post(
                "/internal/v1/memory/index/upsert",
                json={**asdict(value), "event_id": event},
                headers=headers,
            )
            assert response.status_code == 200
            assert response.json()["state"] == "READY"
        assert len(sent) == 1
        with monkeypatch.context() as later:
            later.setattr(time, "time", lambda: now + 100)
            result = await index.search(
                scope,
                space,
                (identity,),
                vector=(1.0,) + (0.0,) * 1023,
                terms=("Chinese",),
                limit=30,
            )
            assert (
                result[0][0].identity == identity and result[1][0].identity == identity
            )
        authorization = {
            "scope": asdict(scope),
            "space": asdict(space),
            "execution": asdict(value.execution),
            "allowed": [asdict(identity)],
            "expires_at": value.expires_at,
            "query_embedding_allowed": True,
            "top_k": 8,
        }
        for _ in range(2):
            response = await api.post(
                "/internal/v1/memory/index/recall",
                json={
                    "authorization": authorization,
                    "query": "language preference",
                    "terms": ["Chinese"],
                },
                headers=headers,
            )
            assert response.status_code == 200
            assert response.json()["query_embedding_status"] == "USED"
            assert (
                response.json()["candidates"][0]["identity"]["item_id"]
                == identity.item_id
            )
        assert len(sent) == 2
    ledger.authorize(replace(plan, budget_id="budget-2"), prices)
    newer = replace(
        value,
        event_id="generation-2",
        identity=replace(identity, generation=2, version_id="version-2"),
        execution=replace(value.execution, task_id="task-2", execution_id="run-2"),
    )
    async with api_frame(newer) as api:
        assert (
            await api.post(
                "/internal/v1/memory/index/upsert", json=asdict(newer), headers=headers
            )
        ).status_code == 200
        assert len(sent) == 3
        deletion = {
            "event_id": "old-generation-delete",
            "scope": asdict(scope),
            "item_id": identity.item_id,
            "generation": 1,
            "deletion_epoch": 0,
        }
        assert (
            await api.post(
                "/internal/v1/memory/index/delete", json=deletion, headers=headers
            )
        ).json()["state"] == "DELETED"
        assert (
            await index.search(
                scope,
                space,
                (newer.identity,),
                vector=None,
                terms=("Chinese",),
                limit=30,
            )
        )[1][0].identity == newer.identity
        expiry = await index.expire(None, now=now + 3601, limit=100)
        assert len(expiry["index_receipts"]) == 1
        assert expiry["index_receipts"][0]["generation"] == 2
        assert expiry["query_scrubbed"] == 1 and not expiry["remaining"]
        assert (await index._one("SELECT COUNT(*) FROM {schema}.memory_index_entries"))[
            0
        ] == 0
        assert (
            await index._one("SELECT COUNT(*) FROM {schema}.memory_index_task_slots")
        )[0] == 2
        assert await index._one(
            "SELECT state,embedding,item_refs FROM {schema}.memory_query_operations WHERE tenant_id=%s AND task_id=%s",
            (scope.tenant_id, "task-1"),
        ) == ("DELETED", None, "[]")
        deletion = {**deletion, "event_id": "source-forget", "deletion_epoch": 1}
        assert (
            await api.post(
                "/internal/v1/memory/index/delete", json=deletion, headers=headers
            )
        ).json()["state"] == "DELETED"
        assert (
            await api.post(
                "/internal/v1/memory/index/upsert",
                json={**asdict(newer), "event_id": "late-upsert"},
                headers=headers,
            )
        ).status_code == 409
        assert await index.search(
            scope, space, (newer.identity,), vector=None, terms=("Chinese",), limit=30
        ) == ((), ())
        assert len(sent) == 3
    query_row = await index._one(
        "SELECT state,embedding FROM {schema}.memory_query_operations WHERE tenant_id=%s AND task_id=%s",
        (scope.tenant_id, "task-1"),
    )
    assert query_row == ("DELETED", None)
    assert (
        ledger.snapshot("budget-1")["calls"] == 2
        and ledger.snapshot("budget-2")["calls"] == 1
    )
