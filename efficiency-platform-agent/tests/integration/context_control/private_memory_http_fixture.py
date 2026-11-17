"""D17J显式本机真实HTTP/MySQL装配，模型边界唯一Fake，不读取生产env文件。"""

import asyncio
import base64
import json
import os
import re
from dataclasses import replace

import uvicorn
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from efficiency_platform_agent.agents.customer_service.graph import CustomerServiceGraph
from efficiency_platform_agent.agents.customer_service.model_gateway import (
    ReleaseStructuredModelGateway,
)
from efficiency_platform_agent.agents.customer_service.release_repository import (
    MySqlReleaseRepository,
)
from efficiency_platform_agent.agents.customer_service.retrieval_snapshot_repository import (
    MySqlRetrievalSnapshotRepository,
)
from efficiency_platform_agent.agents.customer_service.service import (
    CustomerServiceRunService,
)
from efficiency_platform_agent.api.app import create_app
from efficiency_platform_agent.context.controller import ContextController
from efficiency_platform_agent.context.dispatch import (
    ContextDispatch,
    ControlledModelProvider,
)
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
from efficiency_platform_agent.harness.hr_factory import internal_hr_authorizer
from efficiency_platform_agent.harness.local_real_factory import (
    build_local_agent_application,
)
from efficiency_platform_agent.memory.execution_authority import (
    StoredMemoryPacketValidator,
)
from efficiency_platform_agent.persistence.context_manifest import (
    MySqlContextManifestStore,
)
from efficiency_platform_agent.persistence.context_stage import MySqlContextStageStore
from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher
from efficiency_platform_agent.persistence.mysql_runtime import (
    MySqlRunEventStore,
    MySqlRunRepository,
)
from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)
from tests.api.test_conversation_routes import intent
from tests.integration.context_control.business_http_fixture import (
    MODEL,
    RELEASE,
    published_metadata,
    release_bundle,
)
from tests.integration.context_control.test_memory_execution_mysql import configured_url
from tests.unit.harness.test_local_real_factory import synthetic_settings

print("D17J_FIXTURE_IMPORTS_DONE", flush=True)


class SafeFailureRecorder:
    def record(self, record):
        if record.error_code is None:
            return
        values = {}
        for key, pattern in (("error_code", r"[A-Z][A-Z0-9_]{0,127}"),
                             ("error_type", r"[A-Za-z][A-Za-z0-9_]{0,127}"),
                             ("error_location", r"[A-Za-z0-9_.-]+:[0-9]+:[A-Za-z0-9_<>]+")):
            value = getattr(record, key, None)
            if isinstance(value, str) and re.fullmatch(pattern, value):
                values[key] = value
        print("D17J_SAFE_FAILURE " + json.dumps(values), flush=True)


def failure_code(value):
    raw = json.loads(value) if isinstance(value, str) else value
    code = (raw.get("failure") or {}).get("code")
    return code if isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", code) else None


class FixedBoundary(FakeModelProvider):
    def __init__(self):
        super().__init__("d13-explicit-fixed-boundary", [])
        self.observations = []

    async def complete(self, request):
        binding, stage = current_run_context(), current_model_stage()
        self.observations.append(
            {
                "execution_id": binding.execution_id,
                "node_id": stage.node_id,
                "preference_count": sum(
                    "已确认的响应展示偏好" in str(message.content)
                    for message in request.messages
                ),
                "legacy_present": any(
                    "legacy-unsafe-marker" in str(message.content)
                    for message in request.messages
                ),
                "prior_answer_present": any(
                    "synthetic display result" in str(message.content)
                    for message in request.messages
                ),
                "history_markers": [
                    marker
                    for marker in (
                        "d13-history-first-0",
                        "d13-history-first-1",
                        "d13-history-follow-up",
                        "d13-csr-first-u1",
                        "d13-csr-first-u2",
                    )
                    if any(
                        marker in str(message.content) for message in request.messages
                    )
                ],
            }
        )
        if stage.node_id == "customer-service:intent":
            answer = json.dumps(
                {
                    "intent_type": "GENERAL_QUERY",
                    "requires_company_knowledge": False,
                    "requires_general_advice": True,
                    "normalized_question": "synthetic general advice",
                }
            )
        elif stage.node_id == "customer-service:answer_general":
            answer = json.dumps(
                {
                    "contract_version": "customer-service-answer/1",
                    "answer_mode": "GENERAL_ADVICE",
                    "general_advice": {"paragraphs": ["synthetic display result"]},
                }
            )
        else:
            answer = (
                intent()
                .model_copy(
                    update={"task_type": "general_chat", "needs_multi_agent": False}
                )
                .model_dump_json()
                if request.contract_version == "intent/1"
                else "synthetic display result"
            )
        return ProviderResult(
            request.contract_version,
            ProviderMessage("assistant", answer),
            ProviderUsage(1, 1, 0, 0, 0),
        )


async def main():
    if os.environ.get("MEMORY_IT_ENABLED") != "1":
        raise ValueError("MEMORY_IT_LOCAL_ONLY")
    engine = create_async_engine(configured_url())
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    print("D17J_FIXTURE_DB_READY", flush=True)
    key = os.environ["MEMORY_IT_CONTEXT_HMAC_KEY"].encode()
    secret = os.environ["MEMORY_IT_INTERNAL_SECRET"]
    cipher = MemorySnapshotCipher(
        "isolated-test",
        {
            "isolated-test": base64.b64decode(
                os.environ["MEMORY_IT_MEMORY_ENCRYPTION_KEY"], validate=True
            )
        },
    )
    from tests.integration.memory.lifecycle_postgres import production_memory_runtime

    pg_context = production_memory_runtime(engine, cipher)
    components = await pg_context.__aenter__()
    memory_store = components.store
    manifest_store = MySqlContextManifestStore(engine)
    published = {}
    for model in ("synthetic-fast", "synthetic-balanced", "synthetic-strong"):
        capacity = ModelCapacity(
            "deepseek",
            model,
            "fixture/1",
            200000,
            160000,
            4000,
            "conservative-utf8/1",
            "openai-chat/1",
            "NO_REASONING",
            True,
            "explicit-fake-only",
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
            published[("deepseek", model, node)] = ContextMetadata(
                node,
                "window/1",
                "1",
                "1",
                "1",
                1,
                capacity,
                WindowLimits(200000, 160000, reserve, 10000, 120000),
                JsonObject((*options.items, ("logical_model", model))),
            )
    authority = ServerDispatchAuthority(
        published
        | {
            key: replace(value, policy_version="window/1")
            for key, value in published_metadata().items()
            if key[2].startswith("customer-service:")
        },
        {
            "intent": ("operations", "intent"),
            "direct": ("operations", "assistant_response"),
            "customer-service:intent": ("customer-service", "intent"),
            "customer-service:answer_general": (
                "customer-service",
                "assistant_response",
            ),
        },
        memory_execution_store=memory_store,
    )
    authority.assert_ready()
    controller = ContextController(
        ConservativeRequestTokenCounter(),
        manifest_store,
        key,
        validator=StoredMemoryPacketValidator(memory_store),
    )
    dispatch = ContextDispatch(
        controller,
        manifest_store,
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
    from efficiency_platform_agent.core.enums import StrategyMode
    from efficiency_platform_agent.orchestration.context_gate import FencedModelProvider
    from efficiency_platform_agent.orchestration.fenced_checkpoint import (
        FencedCheckpointStore,
    )

    provider = FixedBoundary()
    bundle = build_local_agent_application(
        settings,
        provider=FencedModelProvider(provider, components.registry, "official"),
        test_mode=True,
        context_dispatch=dispatch,
    )
    graph = bundle.runtime.graph_runtime
    recorder = SafeFailureRecorder()
    graph.diagnostic_recorder = recorder
    bundle.runtime.diagnostic_recorder = recorder
    graph.registry.get(StrategyMode.DIRECT).builder.checkpointer = components.saver
    graph.memory_registry = components.registry
    graph.checkpoints = FencedCheckpointStore(
        components.owned, components.registry, serializer=components.serializer
    )
    bundle.runtime.repository = MySqlRunRepository(engine, cipher)
    bundle.runtime.event_store = MySqlRunEventStore(engine)
    bundle.runtime.memory_execution_store = memory_store
    releases = MySqlReleaseRepository(engine)
    await releases.save(RELEASE, release_bundle())
    customer_provider = ControlledModelProvider(
        FencedModelProvider(provider, components.registry, "NO_CHECKPOINT"),
        dispatch,
        "deepseek",
        MODEL,
        paid_transport=False,
    )
    customer = CustomerServiceRunService(
        CustomerServiceGraph(None),
        releases,
        lambda release: ReleaseStructuredModelGateway(customer_provider, release),
        retrieval_snapshots=MySqlRetrievalSnapshotRepository(engine),
        context_required=True,
        memory_execution_store=memory_store,
    )
    app = create_app(
        bundle.runtime,
        conversation_service=bundle.conversation,
        event_hub=bundle.event_hub,
        context_internal_authorizer=internal_hr_authorizer(secret),
        memory_enabled=True,
        memory_execution_store=memory_store,
        customer_service_run_service=customer,
        memory_manifest_reader=manifest_store.execution_manifests,
        memory_erase_threads=components.erasure.prepare_and_erase,
        memory_cleanup_journal=components.journal,
        memory_resume_execution=components.registry.resume,
        runtime_mode="d13_real_mysql_fixed_provider",
    )

    @app.exception_handler(RequestValidationError)
    async def schema_error(request: Request, error: RequestValidationError):
        print(
            json.dumps(
                {
                    "phase": "request_schema",
                    "status": 422,
                    "validation": [
                        {"loc": item["loc"], "type": item["type"]}
                        for item in error.errors()
                    ],
                }
            ),
            flush=True,
        )
        return JSONResponse(
            status_code=422, content={"error": {"code": "INVALID_SCHEMA"}}
        )

    @app.get("/__memory_it__/proof")
    async def proof(request: Request):
        if request.headers.get("Authorization") != "Bearer " + secret:
            raise HTTPException(401)
        await bundle.runtime.wait_for_background_tasks()
        await asyncio.gather(
            *(run.task for run in customer._runs.values() if run.task is not None)
        )
        async with engine.connect() as connection:
            manifests = (
                (
                    await connection.execute(
                        text("SELECT metadata_json FROM agent_context_manifest")
                    )
                )
                .scalars()
                .all()
            )
            runs = (
                await connection.execute(
                    text("SELECT run_id,status,state_json FROM agent_run")
                )
            ).all()
        return {
            "provider_mode": "FIXED_FAKE",
            "requests": provider.observations,
            "manifests": [
                json.loads(value) if isinstance(value, str) else value
                for value in manifests
            ],
            "runs": [
                {
                    "id": run[0],
                    "status": run[1],
                    "failure_code": failure_code(run[2]),
                    "encrypted": '"ciphertext"'
                    in (run[2] if isinstance(run[2], str) else json.dumps(run[2])),
                }
                for run in runs
            ],
            "customer_runs": [
                {"id": str(run.view.run_id), "status": run.view.status.value}
                for run in customer._runs.values()
            ],
        }

    @app.post("/__memory_it__/shutdown")
    async def shutdown(request: Request):
        if request.headers.get("Authorization") != "Bearer " + secret:
            raise HTTPException(401)
        server.should_exit = True
        return {"stopping": True}

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=int(os.environ["MEMORY_IT_AGENT_PORT"]),
            log_level="critical",
            lifespan="off",
        )
    )
    print("D17J_FIXTURE_FACTORY_READY", flush=True)
    try:
        print("D17J_FIXTURE_UVICORN_START", flush=True)
        await server.serve()
    finally:
        await bundle.close()
        await pg_context.__aexit__(None, None, None)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
