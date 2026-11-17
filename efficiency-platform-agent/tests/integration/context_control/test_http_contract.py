"""真实loopback HTTP与MySQL门禁，只有供应商边界使用固定Fake。"""

import asyncio
import json
import socket
from contextlib import asynccontextmanager
from secrets import token_hex

import httpx
import pytest
import uvicorn
from fastapi import HTTPException, Request
from pydantic import SecretStr
from sqlalchemy import text

from efficiency_platform_agent.context.controller import ContextController
from efficiency_platform_agent.context.dispatch import ContextDispatch
from efficiency_platform_agent.core.context_control import ModelCapacity, WindowLimits
from efficiency_platform_agent.core.context_dispatch import current_model_stage
from efficiency_platform_agent.core.context_ports import ContextMetadata
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.core.run_context_binding import current_run_context
from efficiency_platform_agent.harness.context_authority import ServerDispatchAuthority
from efficiency_platform_agent.harness.local_real_factory import (
    build_local_agent_application,
)
from efficiency_platform_agent.persistence.context_manifest import (
    MySqlContextManifestStore,
)
from efficiency_platform_agent.persistence.context_stage import MySqlContextStageStore
from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)
from tests.api.test_conversation_routes import intent
from tests.unit.harness.test_local_real_factory import synthetic_settings


class SyntheticBoundaryProvider(FakeModelProvider):
    def __init__(self, published):
        super().__init__("memory-integration-synthetic", [])
        self.requests = []
        self.observations = []
        self.fixture_nonce = token_hex(16)
        self.published = published

    async def complete(self, request):
        self.requests.append(request)
        stage, binding = current_model_stage(), current_run_context()
        options = dict(request.options.items)
        capacity = self.published[
            ("deepseek", options["logical_model"], stage.node_id)
        ].capacity
        measurement = ConservativeRequestTokenCounter().measure(request, capacity)
        self.observations.append(
            {
                "execution_id": binding.execution_id,
                "node_id": stage.node_id,
                "input_upper_bound": measurement.total_upper_bound,
                "tool_count": len(options.get("tools", ())),
            }
        )
        if request.contract_version == "intent/1":
            content = (
                intent()
                .model_copy(
                    update={
                        "task_type": "general_chat",
                        "needs_multi_agent": False,
                    }
                )
                .model_dump_json()
            )
        else:
            content = "合成回复"
        return ProviderResult(
            request.contract_version,
            ProviderMessage("assistant", content),
            ProviderUsage(2, 3, 0, 0, 1),
        )


@asynccontextmanager
async def running_context_app(engine):
    # 合成凭据只在本次本机fixture内使用，绝不访问供应商。
    key = b"memory-it-only-stable-hmac-key-000000"
    secret = "memory-it-only-internal-secret-00000"
    published = {}
    for model in ("synthetic-fast", "synthetic-balanced", "synthetic-strong"):
        capacity = ModelCapacity(
            "deepseek",
            model,
            "synthetic/1",
            200000,
            160000,
            4000,
            "conservative-utf8/1",
            "openai-chat/1",
            "NO_REASONING",
            True,
            "synthetic-fixture-not-real-model-capacity",
        )
        for node, options, reserve in (
            (
                "intent",
                JsonObject(
                    (
                        ("temperature", 0),
                        ("max_tokens", 2000),
                        ("response_format", JsonObject((("type", "json_object"),))),
                    )
                ),
                4000,
            ),
            ("direct", JsonObject((("max_tokens", 2000),)), 2000),
        ):
            limits = WindowLimits(200000, 160000, reserve, 10000, 120000)
            runtime_options = JsonObject((*options.items, ("logical_model", model)))
            published[("deepseek", model, node)] = ContextMetadata(
                node, "1", "1", "1", "1", 1, capacity, limits, runtime_options
            )
    store = MySqlContextManifestStore(engine)
    controller = ContextController(ConservativeRequestTokenCounter(), store, key)
    authority = ServerDispatchAuthority(
        published,
        {"intent": ("operations", "intent"), "direct": ("operations", "answer")},
    )
    authority.assert_ready()
    dispatch = ContextDispatch(
        controller,
        store,
        authority,
        stage_store=MySqlContextStageStore(engine, key),
        hmac_key=key,
    )
    settings = synthetic_settings().model_copy(
        update={
            "context_enabled": True,
            "context_hmac_key": SecretStr(key.decode()),
            "context_internal_secret": SecretStr(secret),
        }
    )
    provider = SyntheticBoundaryProvider(published)
    bundle = build_local_agent_application(
        settings, provider=provider, test_mode=True, context_dispatch=dispatch
    )

    @bundle.app.get("/__memory_it__/proof")
    async def fixture_proof(request: Request):
        if request.headers.get("Authorization") != "Bearer " + secret:
            raise HTTPException(status_code=401)
        return {
            "provider_mode": "FIXED_FAKE",
            "fixture_nonce": provider.fixture_nonce,
            "requests": provider.observations,
        }

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    server = uvicorn.Server(
        uvicorn.Config(bundle.app, log_level="critical", lifespan="off")
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("synthetic HTTP fixture stopped")
                await asyncio.sleep(0.01)
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{listener.getsockname()[1]}",
            timeout=30,
            trust_env=False,
        ) as client:
            yield client, bundle, provider, secret
    finally:
        server.should_exit = True
        try:
            async with asyncio.timeout(10):
                await task
        finally:
            if not task.done():
                task.cancel()
            listener.close()
            await bundle.close()


def scoped_body(tenant, user, session, request_id):
    return {
        "message": f"解释品牌定位 [{tenant}:{user}:{session}]",
        "request_id": request_id,
        "user_id": user,
        "memory_context": {
            "schema_version": "memory-context/1",
            "memory_mode": "DISABLED",
            "scope": {
                "tenant_id": tenant,
                "user_id": user,
                "domain": "operations",
                "top_level_agent_id": "operations",
                "session_kind": "CONVERSATION",
                "session_id": session,
            },
            "packet": None,
        },
    }


@pytest.mark.asyncio
async def test_real_http_auth_scope_and_persistent_final_request(context_mysql):
    async with running_context_app(context_mysql) as (client, bundle, provider, secret):
        rejected = await client.post(
            "/v1/conversations/s/messages",
            headers={"X-Tenant-ID": "synthetic-t1"},
            json=scoped_body("synthetic-t1", "synthetic-u1", "s", "unauth"),
        )
        assert rejected.status_code == 401
        mismatch = await client.post(
            "/v1/conversations/s/messages",
            headers={
                "X-Tenant-ID": "synthetic-t1",
                "Authorization": "Bearer " + secret,
            },
            json=scoped_body("synthetic-t2", "synthetic-u1", "s", "forged"),
        )
        assert mismatch.status_code == 403
        wrong_agent = scoped_body("synthetic-t1", "synthetic-u1", "s", "wrong-agent")
        wrong_agent["memory_context"]["scope"].update(
            domain="hr",
            top_level_agent_id="hr",
            session_kind="TASK_ONLY",
            session_id=None,
        )
        cross_agent = await client.post(
            "/v1/conversations/s/messages",
            headers={
                "X-Tenant-ID": "synthetic-t1",
                "Authorization": "Bearer " + secret,
            },
            json=wrong_agent,
        )
        assert cross_agent.status_code == 403
        assert provider.requests == []
        scopes = []
        for tenant in ("synthetic-t1", "synthetic-t2"):
            for user in ("synthetic-u1", "synthetic-u2"):
                for index in (1, 2):
                    session = f"session-{index}"
                    response = await client.post(
                        f"/v1/conversations/{session}/messages",
                        headers={
                            "X-Tenant-ID": tenant,
                            "Authorization": "Bearer " + secret,
                        },
                        json=scoped_body(tenant, user, session, f"req-{user}-{index}"),
                    )
                    assert response.status_code == 201, response.status_code
                    await bundle.runtime.wait_for_background_tasks()
                    run_id = response.json()["run_id"]
                    run = await bundle.runtime.get_run(run_id, tenant)
                    assert run.status.value == "succeeded", (
                        run.status.value,
                        run.error.code if run.error else None,
                    )
                    scopes.append((tenant, user, session, run_id))
        markers = {
            f"[{tenant}:{user}:{session}]" for tenant, user, session, _ in scopes
        }
        direct_requests = [
            request
            for request in provider.requests
            if request.contract_version == "general-conversation/1"
        ]
        assert len(direct_requests) == 8
        for request in direct_requests:
            content = " ".join(str(message.content) for message in request.messages)
            assert sum(marker in content for marker in markers) == 1
        async with context_mysql.connect() as connection:
            manifests = (
                (
                    await connection.execute(
                        text("SELECT metadata_json FROM agent_context_manifest")
                    )
                )
                .scalars()
                .all()
            )
            states = (
                (
                    await connection.execute(
                        text("SELECT status FROM agent_context_operation")
                    )
                )
                .scalars()
                .all()
            )
            stages = (
                await connection.execute(
                    text("SELECT status,current_slot FROM agent_context_stage")
                )
            ).all()
        assert (
            len(provider.requests) == len(manifests) == len(states) == len(stages) == 16
        )
        assert set(states) == {"SUCCEEDED"}
        assert set(stages) == {("SUCCEEDED", 1)}
        parsed = [json.loads(row) if isinstance(row, str) else row for row in manifests]
        observed = {
            (
                row["scope"]["conversation"]["tenant_id"],
                row["scope"]["conversation"]["user_id"],
                row["scope"]["conversation"]["session_id"],
                row["scope"]["execution_id"],
            )
            for row in parsed
        }
        assert observed == set(scopes)
        assert all("解释品牌定位" not in str(row) for row in parsed)
        assert all(row["measurement"]["total_upper_bound"] > 0 for row in parsed)
