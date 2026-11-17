import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from efficiency_platform_agent.core.context_control import ModelCapacity, WindowLimits
from efficiency_platform_agent.core.context_dispatch import model_stage
from efficiency_platform_agent.core.context_ports import ContextMetadata
from efficiency_platform_agent.core.memory import ConversationScope
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    bind_conversation_scope,
    bind_run_context,
)
from efficiency_platform_agent.harness.context_authority import ServerDispatchAuthority


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user,session,text",
    [
        ("other", "s", "x"),
        ("u", "other", "x"),
        ("u", "s", "different"),
        ("u", "s", "x"),
    ],
)
async def test_pending_checks_original_identity_before_returning_run(
    user, session, text
):
    from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
    from efficiency_platform_agent.harness.errors import HarnessError
    from tests.api.test_conversation_routes import service

    entered, release = asyncio.Event(), asyncio.Event()

    class Runtime:
        calls = 0

        async def create_and_schedule_pipeline(self, request, prepare, *, on_queued):
            self.calls += 1
            entered.set()
            await release.wait()
            await on_queued(SimpleNamespace(run_id="original-run"))

    runtime = Runtime()
    facade = service(runtime, None)

    async def submit(who, session_id, message):
        scope = ConversationScope(
            "t", who, "operations", "operations", "CONVERSATION", session_id
        )
        with bind_conversation_scope(scope):
            return await facade.submit(
                session_id,
                "t",
                ConversationMessageV1(message=message, request_id="r", user_id=who),
            )

    original = asyncio.create_task(submit("u", "s", "x"))
    await entered.wait()
    duplicate = asyncio.create_task(submit(user, session, text))
    await asyncio.sleep(0)
    release.set()
    try:
        if (user, session, text) == ("u", "s", "x"):
            assert (await duplicate).run_id == "original-run"
        else:
            with pytest.raises(HarnessError, match="request_id"):
                await duplicate
    finally:
        await original
    assert runtime.calls == 1


def assets(options=None):
    capacity = ModelCapacity(
        "fake",
        "fake",
        "1",
        1000,
        None,
        100,
        "fake/1",
        "fake/1",
        "none",
        True,
        "offline",
    )
    return ContextMetadata(
        "node",
        "1",
        "1",
        "1",
        "1",
        0,
        capacity,
        WindowLimits(1000, None, 100, 0, 900),
        options or JsonObject((("max_tokens", 100),)),
    )


@pytest.mark.asyncio
async def test_only_explicit_variants_allow_schema_and_reduced_output():
    first = assets(JsonObject((("max_tokens", 100), ("schema", "first"))))
    repair = replace(
        first,
        output_schema_version="repair",
        options=JsonObject((("max_tokens", 100), ("schema", "repair"))),
    )
    authority = ServerDispatchAuthority(
        {("fake", "fake", "node"): (first, repair)},
        {"node": ("operations", "generate")},
    )
    authority.assert_ready()
    scope = ConversationScope("t", "u", "operations", "operations", "CONVERSATION", "s")
    with (
        bind_run_context(RunContextBinding(scope, "r", "r", 9999999999)),
        model_stage("stage", b"input", node_id="node"),
    ):
        for schema, tokens, allowed in [
            ("first", 100, True),
            ("repair", 40, True),
            ("unknown", 40, False),
            ("repair", 101, False),
        ]:
            request = ProviderRequest(
                "1",
                (ProviderMessage("user", "x"),),
                JsonObject((("max_tokens", tokens), ("schema", schema))),
                1000,
            )
            if allowed:
                plan = await authority.resolve(request, "fake", "fake")
                assert plan.metadata.options == request.options
                assert plan.metadata.limits.output_reserve_tokens == 100
            else:
                with pytest.raises(ValueError, match="OPTIONS_MISMATCH"):
                    await authority.resolve(request, "fake", "fake")


@pytest.mark.parametrize("field", ["policy_version", "capacity"])
def test_variants_cannot_change_stage_policy_or_capacity(field):
    first = assets()
    other = replace(
        first,
        **{
            field: "2"
            if field == "policy_version"
            else replace(first.capacity, model_version="2")
        },
    )
    authority = ServerDispatchAuthority(
        {("fake", "fake", "node"): (first, other)}, {"node": ("operations", "generate")}
    )
    with pytest.raises(ValueError, match="BUNDLE"):
        authority.assert_ready()


@pytest.mark.asyncio
async def test_debug_route_authenticates_task_only_scope_without_extra_user_field():
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from efficiency_platform_agent.api.customer_service_routes import (
        build_customer_service_router,
    )
    from efficiency_platform_agent.core.run_context_binding import (
        current_conversation_scope,
    )
    from efficiency_platform_agent.harness.hr_factory import internal_hr_authorizer

    class Service:
        def __init__(self):
            self.scopes = []

        async def debug(self, body):
            self.scopes.append(current_conversation_scope())
            return {"status": "SUCCEEDED"}

    service = Service()
    app = FastAPI()
    app.include_router(
        build_customer_service_router(service, internal_hr_authorizer("f" * 32))
    )
    body = {
        "contract_version": "customer-service-rag-debug/1",
        "agent_key": "customer-service",
        "tenant_id": "t",
        "question": "x",
        "agent_release_id": "80000000-0000-0000-0000-000000000001",
        "agent_version_id": "80000000-0000-0000-0000-000000000001",
        "rag_policy_version_id": "80000000-0000-0000-0000-000000000001",
        "knowledge_bindings": [
            {
                "knowledge_base_id": "80000000-0000-0000-0000-000000000001",
                "index_release_id": "80000000-0000-0000-0000-000000000001",
            }
        ],
        "memory_context": {
            "scope": {
                "tenant_id": "t",
                "user_id": "real-user",
                "domain": "customer-service",
                "top_level_agent_id": "customer-service",
                "session_kind": "TASK_ONLY",
                "session_id": None,
            }
        },
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        denied = await client.post(
            "/internal/v1/customer-service/rag-debug-runs", json=body
        )
        assert denied.status_code == 401
        good = await client.post(
            "/internal/v1/customer-service/rag-debug-runs",
            json=body,
            headers={"Authorization": "Bearer " + "f" * 32, "X-Tenant-ID": "t"},
        )
        assert good.status_code == 200
        bad = body | {
            "memory_context": {
                "scope": body["memory_context"]["scope"]
                | {"session_kind": "CONVERSATION", "session_id": "chat"}
            }
        }
        response = await client.post(
            "/internal/v1/customer-service/rag-debug-runs",
            json=bad,
            headers={"Authorization": "Bearer " + "f" * 32, "X-Tenant-ID": "t"},
        )
        assert response.status_code == 403
    assert len(service.scopes) == 1 and service.scopes[0].user_id == "real-user"


@pytest.mark.asyncio
async def test_debug_service_binds_real_actor_server_run_and_original_deadline():
    from time import monotonic, time

    from efficiency_platform_agent.agents.customer_service.service import (
        CustomerServiceRunService,
        CustomerServiceScopeError,
    )
    from efficiency_platform_agent.agents.customer_service.state import DebugRequest
    from efficiency_platform_agent.core.execution_control import current_run_control
    from efficiency_platform_agent.core.run_context_binding import current_run_context
    from tests.api.test_customer_service_routes import RELEASE_ID, Graph

    class Bundle(SimpleNamespace):
        def model_copy(self, *, update):
            return Bundle(**update)

    class Releases:
        calls = 0

        async def get(self, release):
            self.calls += 1
            return Bundle()

    class CaptureGraph(Graph):
        binding = None
        request = None

        async def run(self, request, bundle, gateway):
            self.binding = current_run_context()
            self.request = request
            control = current_run_control()
            assert self.binding.deadline_epoch_seconds == int(
                time() + control.deadline - monotonic()
            )
            return await super().run(request, bundle, gateway)

    graph, releases = CaptureGraph(), Releases()
    service = CustomerServiceRunService(
        graph, releases, lambda _: object(), context_required=True
    )
    body = {
        "contract_version": "customer-service-rag-debug/1",
        "agent_key": "customer-service",
        "tenant_id": "t",
        "question": "x",
        "agent_release_id": RELEASE_ID,
        "agent_version_id": RELEASE_ID,
        "rag_policy_version_id": RELEASE_ID,
        "knowledge_bindings": (
            {"knowledge_base_id": RELEASE_ID, "index_release_id": RELEASE_ID},
        ),
    }
    with pytest.raises(CustomerServiceScopeError):
        await service.debug(DebugRequest(**body))
    assert releases.calls == 0 and graph.binding is None
    scope = ConversationScope(
        "t", "actual-user", "customer-service", "customer-service", "TASK_ONLY", None
    )
    from efficiency_platform_agent.contracts.memory import ConversationScopeModel
    from efficiency_platform_agent.contracts.memory_context import MemoryContextEnvelope

    payload = DebugRequest(
        **body,
        memory_context=MemoryContextEnvelope(
            scope=ConversationScopeModel.from_core(scope)
        ),
    )
    with bind_conversation_scope(scope):
        result = await service.debug(payload)
    assert graph.binding.task_id == graph.binding.execution_id == result["debug_run_id"]
    assert graph.binding.conversation == scope
    assert graph.request.user_id == "actual-user" and graph.request.history == ()
