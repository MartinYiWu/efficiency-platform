import asyncio

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.conversation import ConversationMessageV1


def test_envelope_disabled_legacy_is_not_authorized():
    from efficiency_platform_agent.contracts.memory_context import MemoryContextEnvelope

    value = ConversationMessageV1(message="x", request_id="r", user_id="u")
    assert value.memory_context == MemoryContextEnvelope()
    assert value.memory_context.scope is None


@pytest.mark.parametrize("extra", [{"task_id": "forged"}, {"deadline": 999}])
def test_boundary_forbids_client_run_authority(extra):
    from efficiency_platform_agent.contracts.memory_context import MemoryContextEnvelope

    with pytest.raises(ValidationError):
        MemoryContextEnvelope.model_validate(extra)


@pytest.mark.asyncio
async def test_async_binding_is_captured_and_does_not_leak():
    from efficiency_platform_agent.core.memory import ConversationScope
    from efficiency_platform_agent.core.run_context_binding import (
        RunContextBinding,
        bind_run_context,
        current_run_context,
    )

    async def child():
        await asyncio.sleep(0)
        return current_run_context()

    tasks = []
    for user in ("one", "two"):
        scope = ConversationScope(
            "t", user, "operations", "operations", "CONVERSATION", "s"
        )
        with bind_run_context(
            RunContextBinding(scope, "task-" + user, "exec-" + user, 9999999999)
        ):
            tasks.append(asyncio.create_task(child()))
    values = await asyncio.gather(*tasks)
    assert [x.conversation.user_id for x in values] == ["one", "two"]
    assert current_run_context() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "other"),
        ("user_id", "other"),
        ("top_level_agent_id", "hr"),
        ("session_id", "other"),
    ],
)
async def test_authenticated_transport_cannot_cross_scope(field, value):
    from starlette.requests import Request

    from efficiency_platform_agent.api.context_auth import authorize_memory_context
    from efficiency_platform_agent.contracts.memory_context import MemoryContextEnvelope

    data = {
        "tenant_id": "t",
        "user_id": "u",
        "domain": "operations",
        "top_level_agent_id": "operations",
        "session_kind": "CONVERSATION",
        "session_id": "s",
    }
    data[field] = value
    try:
        envelope = MemoryContextEnvelope.model_validate({"scope": data})
    except ValidationError:
        return

    async def authorize(request):
        return "t"

    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        await authorize_memory_context(
            Request({"type": "http", "headers": []}),
            envelope,
            authorize,
            tenant="t",
            user="u",
            domain="operations",
            session_id="s",
        )


@pytest.mark.asyncio
async def test_scoped_envelope_without_internal_auth_fails():
    from fastapi import HTTPException
    from starlette.requests import Request

    from efficiency_platform_agent.api.context_auth import authorize_memory_context
    from efficiency_platform_agent.contracts.memory_context import MemoryContextEnvelope

    envelope = MemoryContextEnvelope.model_validate(
        {
            "scope": {
                "tenant_id": "t",
                "user_id": "u",
                "domain": "hr",
                "top_level_agent_id": "hr",
                "session_kind": "TASK_ONLY",
                "session_id": None,
            }
        }
    )
    with pytest.raises(HTTPException):
        await authorize_memory_context(
            Request({"type": "http", "headers": []}),
            envelope,
            None,
            tenant="t",
            user="u",
            domain="hr",
            session_id=None,
        )


def test_persisted_run_binding_uses_run_not_session():
    from efficiency_platform_agent.core.memory import ConversationScope
    from efficiency_platform_agent.core.run_context_binding import (
        binding_from_metadata,
        metadata_scope,
    )

    scope = ConversationScope(
        "t", "u", "operations", "operations", "CONVERSATION", "session"
    )
    metadata = metadata_scope(scope)
    bound = binding_from_metadata(metadata, "server-run", 2000000000)
    assert bound.task_id == bound.execution_id == "server-run"
    assert bound.conversation == scope


def test_enabled_configuration_requires_explicit_keys():
    from efficiency_platform_agent.configuration.integration import (
        S7IntegrationSettings,
    )

    with pytest.raises(ValidationError):
        S7IntegrationSettings(context_enabled=True)


@pytest.mark.asyncio
async def test_authority_requires_trusted_run_and_verified_capacity():
    from efficiency_platform_agent.core.run import (
        JsonObject,
        ProviderMessage,
        ProviderRequest,
    )
    from efficiency_platform_agent.harness.context_authority import (
        ServerDispatchAuthority,
    )

    request = ProviderRequest(
        "provider/1", (ProviderMessage("user", "forged tenant=t"),), JsonObject(), 1000
    )
    authority = ServerDispatchAuthority({})
    with pytest.raises(ValueError, match="RUN_BINDING_REQUIRED"):
        await authority.resolve(request, "fake", "fake")
    from efficiency_platform_agent.core.memory import ConversationScope
    from efficiency_platform_agent.core.run_context_binding import (
        RunContextBinding,
        bind_run_context,
    )

    with (
        bind_run_context(
            RunContextBinding(
                ConversationScope("t", "u", "hr", "hr", "TASK_ONLY", None),
                "r",
                "r",
                9999999999,
            )
        ),
        pytest.raises(ValueError, match="CAPACITY_NOT_PUBLISHED"),
    ):
        await authority.resolve(request, "fake", "fake")


def test_java_legacy_null_envelope_normalizes_disabled():
    value = ConversationMessageV1(
        message="x", request_id="r", user_id="u", memory_context=None
    )
    assert value.memory_context.scope is None


@pytest.mark.asyncio
async def test_task_only_authority_preserves_original_deadline_without_history_read():
    from efficiency_platform_agent.core.context_control import (
        ModelCapacity,
        WindowLimits,
    )
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
        bind_run_context,
    )
    from efficiency_platform_agent.harness.context_authority import (
        ServerDispatchAuthority,
    )

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
    metadata = ContextMetadata(
        "node",
        "1",
        "1",
        "1",
        "1",
        0,
        capacity,
        WindowLimits(1000, None, 100, 0, 900),
        JsonObject(),
    )
    authority = ServerDispatchAuthority(
        {("fake", "fake", "node"): metadata}, {"node": ("hr", "evaluate")}
    )
    request = ProviderRequest(
        "1", (ProviderMessage("user", "current HR facts"),), JsonObject(), 1000
    )
    binding = RunContextBinding(
        ConversationScope("t", "u", "hr", "hr", "TASK_ONLY", None),
        "run",
        "run",
        9999999999,
    )
    with (
        bind_run_context(binding),
        model_stage("original-stage", b"original", node_id="node"),
    ):
        plan = await authority.resolve(request, "fake", "fake")
    assert plan.scope.conversation.history_key is None
    assert plan.operation.deadline_epoch_seconds == binding.deadline_epoch_seconds
    assert plan.operation.operation_id == "original-stage"
    assert plan.scope.execution_agent_id == "hr"
    assert plan.packet is None
    assert all(piece.kind != "history" for piece in plan.pieces)


@pytest.mark.asyncio
async def test_harness_persists_scope_and_background_uses_original_run():
    from efficiency_platform_agent.contracts.requests import CreateRunRequestV1
    from efficiency_platform_agent.core.memory import ConversationScope
    from efficiency_platform_agent.core.run_context_binding import (
        bind_conversation_scope,
        current_run_context,
    )
    from efficiency_platform_agent.harness.factory import build_s2_test_service
    from efficiency_platform_agent.harness.service import RunPipelinePreparation

    runtime = build_s2_test_service()
    captured = []

    async def prepare(pipeline):
        captured.append(current_run_context())
        return RunPipelinePreparation(
            CreateRunRequestV1(
                request_id="r", tenant_id="t", user_id="u", input_text="x"
            )
        )

    scope = ConversationScope(
        "t", "u", "operations", "operations", "CONVERSATION", "session"
    )
    request = CreateRunRequestV1(
        request_id="r", tenant_id="t", user_id="u", input_text="x"
    )
    with bind_conversation_scope(scope):
        view = await runtime.create_and_schedule_pipeline(request, prepare)
    await runtime.wait_for_background_tasks()
    record = await runtime.repository.get(view.run_id, "t")
    assert captured[0].conversation == scope
    assert captured[0].execution_id == view.run_id
    assert captured[0].task_id != "session"
    assert (
        captured[0].deadline_epoch_seconds
        == record.budget_state.deadline_epoch_ms // 1000
    )
    assert "context_scope" in dict(record.request.metadata.items)


@pytest.mark.asyncio
async def test_real_route_denies_scoped_body_without_internal_auth():
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from efficiency_platform_agent.api.conversation_routes import (
        build_conversation_router,
    )

    class ForbiddenService:
        async def submit(self, *args):
            pytest.fail("untrusted scope reached service")

    app = FastAPI()
    app.include_router(build_conversation_router(ForbiddenService()))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/conversations/s/messages",
            headers={"X-Tenant-ID": "t"},
            json={
                "message": "x",
                "request_id": "r",
                "user_id": "u",
                "memory_context": {
                    "scope": {
                        "tenant_id": "t",
                        "user_id": "u",
                        "domain": "operations",
                        "top_level_agent_id": "operations",
                        "session_kind": "CONVERSATION",
                        "session_id": "s",
                    }
                },
            },
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_customer_scoped_idempotency_cannot_return_other_users_run():
    from efficiency_platform_agent.agents.customer_service.service import (
        CustomerServiceRunService,
        CustomerServiceScopeError,
    )
    from efficiency_platform_agent.agents.customer_service.state import (
        CustomerServiceRunRequest,
    )
    from efficiency_platform_agent.core.memory import ConversationScope
    from efficiency_platform_agent.core.run_context_binding import (
        bind_conversation_scope,
    )
    from tests.api.test_customer_service_routes import (
        CONVERSATION_ID,
        RELEASE_ID,
        Graph,
        Releases,
    )

    service = CustomerServiceRunService(Graph(), Releases(), lambda _: object())

    def request(user):
        return CustomerServiceRunRequest(
            contract_version="customer-service-run/1",
            request_id="r",
            conversation_id=CONVERSATION_ID,
            tenant_id="t",
            user_id=user,
            agent_release_id=RELEASE_ID,
            message="x",
            history=(),
        )

    with bind_conversation_scope(
        ConversationScope(
            "t",
            "one",
            "customer-service",
            "customer-service",
            "CONVERSATION",
            str(CONVERSATION_ID),
        )
    ):
        await service.submit(request("one"))
    with (
        bind_conversation_scope(
            ConversationScope(
                "t",
                "two",
                "customer-service",
                "customer-service",
                "CONVERSATION",
                str(CONVERSATION_ID),
            )
        ),
        pytest.raises(CustomerServiceScopeError, match="CONTEXT_SCOPE_MISMATCH"),
    ):
        await service.submit(request("two"))
    await asyncio.gather(*(run.task for run in service._runs.values()))


@pytest.mark.parametrize("change", ["output", "window", "input", "capacity-output"])
def test_ready_rejects_limits_not_matching_published_capacity(change):
    from efficiency_platform_agent.core.context_control import (
        ModelCapacity,
        WindowLimits,
    )
    from efficiency_platform_agent.core.context_ports import ContextMetadata
    from efficiency_platform_agent.core.run import JsonObject
    from efficiency_platform_agent.harness.context_authority import (
        ServerDispatchAuthority,
    )

    capacity = ModelCapacity(
        "fake", "fake", "1", 1000, 800, 100, "fake/1", "fake/1", "none", True, "offline"
    )
    limits = WindowLimits(
        1200 if change == "window" else 1000,
        900 if change == "input" else 800,
        200 if change == "capacity-output" else 100,
        0,
        800,
    )
    options = JsonObject((("max_tokens", 4096 if change == "output" else 100),))
    metadata = ContextMetadata("node", "1", "1", "1", "1", 0, capacity, limits, options)
    authority = ServerDispatchAuthority(
        {("fake", "fake", "node"): metadata}, {"node": ("hr", "evaluate")}
    )
    with pytest.raises(ValueError, match="CAPACITY_LIMITS_MISMATCH"):
        authority.assert_ready()


@pytest.mark.asyncio
async def test_resume_rebinds_persisted_original_scope_deadline():
    from types import SimpleNamespace

    from efficiency_platform_agent.contracts.requests import ResumeRunRequestV1
    from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
    from efficiency_platform_agent.core.memory import ConversationScope
    from efficiency_platform_agent.core.run_context_binding import (
        current_run_context,
        metadata_scope,
    )
    from efficiency_platform_agent.harness.factory import build_s2_test_service

    scope = ConversationScope("t", "u", "operations", "operations", "CONVERSATION", "s")
    record = SimpleNamespace(
        run_id="original",
        status=RunStatus.WAITING_INPUT,
        strategy=StrategyMode.DIRECT,
        request=SimpleNamespace(request_id="r", metadata=metadata_scope(scope)),
        budget_state=SimpleNamespace(deadline_epoch_ms=100000),
    )
    runtime = build_s2_test_service()

    async def get(*args):
        return record

    async def resume(*args):
        return current_run_context()

    runtime.repository = SimpleNamespace(get=get)
    runtime._resume_run_with_context = resume
    bound = await runtime.resume_run(
        "original",
        ResumeRunRequestV1(tenant_id="t", checkpoint_id="c", resume_value={}),
    )
    assert bound.conversation == scope
    assert bound.execution_id == "original"
    assert bound.deadline_epoch_seconds == 100


@pytest.mark.asyncio
@pytest.mark.parametrize("length", [65, 128])
async def test_internal_authorizer_accepts_full_contract_tenant_lengths(length):
    from starlette.requests import Request

    from efficiency_platform_agent.harness.hr_factory import internal_hr_authorizer

    tenant = "t" * length
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer " + b"f" * 32),
                (b"x-tenant-id", tenant.encode()),
            ],
        }
    )
    assert await internal_hr_authorizer("f" * 32)(request) == tenant


@pytest.mark.asyncio
async def test_internal_authorizer_rejects_overlong_tenant_and_invalid_bearer():
    from starlette.requests import Request

    from efficiency_platform_agent.harness.hr_factory import internal_hr_authorizer

    authorize = internal_hr_authorizer("f" * 32)
    for tenant, bearer in [
        ("t" * 129, b"Bearer " + b"f" * 32),
        ("t", b"Bearer forged"),
    ]:
        request = Request(
            {
                "type": "http",
                "headers": [
                    (b"authorization", bearer),
                    (b"x-tenant-id", tenant.encode()),
                ],
            }
        )
        with pytest.raises(PermissionError):
            await authorize(request)


@pytest.mark.parametrize("length", [65, 128])
def test_customer_transport_accepts_full_scope_identifier_lengths(length):
    from efficiency_platform_agent.agents.customer_service.state import (
        CustomerServiceRunRequest,
    )
    from tests.api.test_customer_service_routes import CONVERSATION_ID, RELEASE_ID

    value = CustomerServiceRunRequest(
        contract_version="customer-service-run/1",
        request_id="r",
        conversation_id=CONVERSATION_ID,
        tenant_id="t" * length,
        user_id="u" * length,
        agent_release_id=RELEASE_ID,
        message="x",
        history=(),
    )
    assert len(value.tenant_id) == length


@pytest.mark.asyncio
async def test_authority_uses_trusted_specialist_subtask():
    from efficiency_platform_agent.core.context_control import (
        ModelCapacity,
        WindowLimits,
    )
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
        bind_run_context,
    )
    from efficiency_platform_agent.harness.context_authority import (
        ServerDispatchAuthority,
    )

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
    metadata = ContextMetadata(
        "node",
        "1",
        "1",
        "1",
        "1",
        0,
        capacity,
        WindowLimits(1000, None, 100, 0, 900),
        JsonObject(),
    )
    authority = ServerDispatchAuthority(
        {("fake", "fake", "node"): metadata},
        {"node": ("operation.copywriter", "generate")},
    )
    with (
        bind_run_context(
            RunContextBinding(
                ConversationScope(
                    "t", "u", "operations", "operations", "CONVERSATION", "s"
                ),
                "r",
                "r",
                9999999999,
            )
        ),
        model_stage("stage", b"original", node_id="node", subtask_id="task-child"),
    ):
        plan = await authority.resolve(
            ProviderRequest("1", (ProviderMessage("user", "x"),), JsonObject(), 1000),
            "fake",
            "fake",
        )
    assert plan.scope.subtask_id == "task-child"
