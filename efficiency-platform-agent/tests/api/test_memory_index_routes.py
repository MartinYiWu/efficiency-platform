"""ASGI+原运行+持久SQL fixture+PaidHttp MockTransport，无外部服务。"""

import json
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from openai import AsyncOpenAI

from efficiency_platform_agent.api.memory_index_routes import build_memory_index_router
from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.core.memory import MemoryReference, SourceDependency
from efficiency_platform_agent.core.memory_index import MemoryIndexSpace
from efficiency_platform_agent.core.paid_budget import PaidBudgetPlan, PaidPriceLimit
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    bind_run_context,
)
from efficiency_platform_agent.harness.memory_index_runtime import (
    MemoryIndexCleanupRuntime,
    MemoryIndexRuntime,
    source_fingerprint,
)
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.providers.embedding.dashscope import (
    DashScopeEmbeddingProvider,
)
from tests.integration.memory.test_index_lifecycle import Embedding, build, request


async def test_internal_index_http_uses_original_live_frame_and_cpu_recall(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("EFFICIENCY_TASK_AUTHORIZATION_ENABLED", "true")
    dep = SourceDependency("MESSAGE", "source", "1", 0, 0, 0)
    value = request()
    value = replace(
        value,
        identity=replace(value.identity, source_fingerprint=source_fingerprint((dep,))),
        space=MemoryIndexSpace("text-embedding-v4", 1024, "policy"),
        terms=("projection",),
    )
    packet = SimpleNamespace(
        scope=value.execution.conversation,
        task_id="task",
        execution_id="run",
        expires_at=value.expires_at,
        items=(
            MemoryReference("item", "version", "language", value.projection, (dep,)),
        ),
    )
    context = SimpleNamespace(
        packet=packet,
        policy=SimpleNamespace(version="policy", max_paid_operations=1),
        deadline_epoch_seconds=value.expires_at,
        execution_grants=(
            SimpleNamespace(
                node_id="index", execution_agent_id="operations", purpose="memory.index"
            ),
        ),
    )
    record = SimpleNamespace(
        context=context, state="ACTIVE", deadline_epoch_seconds=value.expires_at
    )

    class Store:
        async def get(self, *args):
            return record

    class Sources:
        valid = True

        async def current(self, *args):
            return self.valid

    sources = Sources()
    locks = []

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
        registry = SimpleNamespace(source_authority=sources)
        execution_store = SimpleNamespace(engine=Engine())

        @asynccontextmanager
        async def acquire(self):
            locks.append("pg")
            try:
                yield
            finally:
                locks.pop()

    ledger = SqlitePaidBudgetLedger(
        tmp_path / "paid.sqlite3", task_authorization_enabled=True
    )
    ledger.initialize_task_authorization_schema(tmp_path / "paid-before.sqlite3")
    ledger.authorize(
        PaidBudgetPlan(
            "b",
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
    sent = []

    async def wire(req):
        assert locks == ["pg", "mysql"]
        sent.append(True)
        return httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [1.0] + [0.0] * 1023}],
                "usage": {"input_tokens": 1},
            },
            request=req,
        )

    from efficiency_platform_agent.providers.paid_http import PaidHttpTransport

    client = AsyncOpenAI(
        api_key="fixture-not-secret",
        base_url="https://fixture.invalid",
        max_retries=0,
        http_client=httpx.AsyncClient(
            transport=PaidHttpTransport(
                ledger,
                httpx.MockTransport(wire),
                "embedding",
                allowed_url="https://fixture.invalid/embeddings",
            ),
            trust_env=False,
            follow_redirects=False,
        ),
    )
    index, _ = build(tmp_path / "index.sqlite3", Embedding())
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

    async def authorize(req):
        if req.headers.get("Authorization") != "Bearer fixture":
            raise PermissionError
        return "tenant"

    app = FastAPI()
    app.include_router(build_memory_index_router(runtime, authorize))
    headers = {"Authorization": "Bearer fixture", "X-Tenant-ID": "tenant"}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://fixture"
        ) as api:
            assert (
                await api.post("/internal/v1/memory/index/upsert", json=asdict(value))
            ).status_code == 401
            missing_retention = asdict(value)
            missing_retention.pop("retention_expires_at")
            assert (
                await api.post(
                    "/internal/v1/memory/index/upsert",
                    json=missing_retention,
                    headers=headers,
                )
            ).status_code == 422
            assert (
                await api.post(
                    "/internal/v1/memory/index/upsert",
                    json={**asdict(value), "retention_expires_at": True},
                    headers=headers,
                )
            ).status_code == 422
            with (
                bind_run_context(
                    RunContextBinding(
                        value.execution.conversation,
                        "task",
                        "run",
                        value.expires_at,
                        context,
                    )
                ),
                execution_scope(RunControl()),
                runtime.for_run(),
            ):
                response = await api.post(
                    "/internal/v1/memory/index/upsert",
                    json=asdict(value),
                    headers=headers,
                )
                assert response.status_code == 200, response.text
                assert response.json()["state"] == "READY"
                assert (
                    await api.post(
                        "/internal/v1/memory/index/upsert",
                        json={**asdict(value), "event_id": "other-event"},
                        headers=headers,
                    )
                ).status_code == 200
                auth = {
                    "scope": asdict(value.scope),
                    "space": asdict(value.space),
                    "execution": asdict(value.execution),
                    "allowed": [asdict(value.identity)],
                    "expires_at": value.expires_at,
                    "query_embedding_allowed": False,
                    "top_k": 8,
                }
                response = await api.post(
                    "/internal/v1/memory/index/recall",
                    json={
                        "authorization": auth,
                        "terms": ["projection"],
                        "query": None,
                    },
                    headers=headers,
                )
                assert response.status_code == 200, response.text
                assert response.json()["candidates"][0]["identity"]["item_id"] == "item"
                assert "projection" not in json.dumps(response.json())
                assert (
                    await api.post(
                        "/internal/v1/memory/index/recall",
                        json={"authorization": auth, "query": "paid"},
                        headers=headers,
                    )
                ).status_code == 409
                semantic_auth = {**auth, "query_embedding_allowed": True}
                unknown_space = {
                    **semantic_auth,
                    "space": {**semantic_auth["space"], "embedding_model": "unpriced"},
                }
                assert (
                    await api.post(
                        "/internal/v1/memory/index/recall",
                        json={
                            "authorization": unknown_space,
                            "query": "find preference",
                        },
                        headers=headers,
                    )
                ).status_code == 409
                assert len(sent) == 1
                semantic = await api.post(
                    "/internal/v1/memory/index/recall",
                    json={"authorization": semantic_auth, "query": "find preference"},
                    headers=headers,
                )
                assert semantic.status_code == 200, semantic.text
                assert semantic.json()["query_embedding_status"] == "USED"
                assert len(sent) == 2
                assert (
                    await api.post(
                        "/internal/v1/memory/index/recall",
                        json={
                            "authorization": semantic_auth,
                            "query": "find preference",
                        },
                        headers=headers,
                    )
                ).status_code == 200
                assert (
                    await api.post(
                        "/internal/v1/memory/index/recall",
                        json={
                            "authorization": semantic_auth,
                            "query": "different query",
                        },
                        headers=headers,
                    )
                ).status_code == 409
                assert (
                    await api.post(
                        "/internal/v1/memory/index/recall",
                        json={"authorization": semantic_auth, "query": "q" * 2049},
                        headers=headers,
                    )
                ).status_code == 409
                assert len(sent) == 2
                sources.valid = False
                assert (
                    await api.post(
                        "/internal/v1/memory/index/upsert",
                        json=asdict(value),
                        headers=headers,
                    )
                ).status_code == 409
            assert len(sent) == 2
            assert (
                await api.post(
                    "/internal/v1/memory/index/upsert",
                    json=asdict(value),
                    headers=headers,
                )
            ).status_code == 409
            deletion = {
                "event_id": "delete",
                "scope": asdict(value.scope),
                "item_id": "item",
                "generation": 1,
                "deletion_epoch": 1,
            }
            assert (
                await api.post(
                    "/internal/v1/memory/index/delete", json=deletion, headers=headers
                )
            ).json()["state"] == "DELETED"
    finally:
        await client.close()


async def test_explicit_cleanup_backend_needs_no_paid_ledger_or_live_frame(tmp_path):
    index, service = build(tmp_path / "cleanup.sqlite3", Embedding())
    value = request()
    await service.upsert(value)
    service.enabled = False
    from efficiency_platform_agent.core.memory_index import IndexDelete

    await service.delete(IndexDelete("disabled-writer", value.scope, "item", 1, 0))
    runtime = MemoryIndexCleanupRuntime(index)

    async def authorize(req):
        if req.headers.get("Authorization") != "Bearer cleanup":
            raise PermissionError
        return "tenant"

    app = FastAPI()
    app.include_router(build_memory_index_router(runtime, authorize))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://fixture"
    ) as client:
        deletion = {
            "event_id": "cleanup",
            "scope": asdict(value.scope),
            "item_id": "item",
            "generation": 1,
            "deletion_epoch": 1,
        }
        assert (
            await client.post("/internal/v1/memory/index/delete", json=deletion)
        ).status_code == 401
        headers = {"Authorization": "Bearer cleanup", "X-Tenant-ID": "tenant"}
        assert (
            await client.post(
                "/internal/v1/memory/index/delete", json=deletion, headers=headers
            )
        ).json()["state"] == "DELETED"
        assert (
            await client.post(
                "/internal/v1/memory/index/upsert", json=asdict(value), headers=headers
            )
        ).status_code == 409
