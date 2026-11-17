"""真实请求边界的离线发送、窗口和回执证明。"""

from dataclasses import replace

import pytest

from efficiency_platform_agent.context.controller import ContextController
from efficiency_platform_agent.context.policy import ContextPiece, ContextPolicy
from efficiency_platform_agent.core.context_control import (
    ModelCapacity,
    TokenMeasurement,
    WindowLimits,
)
from efficiency_platform_agent.core.context_ports import (
    ContextMetadata,
    ContextOperation,
    OperationReceipt,
)
from efficiency_platform_agent.core.memory import ConversationScope, ExecutionScope
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
)


class FakeStore:
    def __init__(self):
        self.manifests = {}
        self.receipts = {}

    async def save_manifest_once(self, manifest, operation):
        key = (manifest.scope, manifest.operation_id)
        previous = self.manifests.get(key)
        if previous is not None and previous != manifest:
            raise ValueError("CONTEXT_MANIFEST_CONFLICT_409")
        self.manifests[key] = manifest
        self.receipts.setdefault(
            key,
            OperationReceipt(
                manifest.canonical_request_hmac,
                "NOT_SENT",
                operation.deadline_epoch_seconds,
            ),
        )
        return manifest

    async def get_operation_receipt(self, scope, operation_id):
        return self.receipts.get((scope, operation_id))

    async def mark_sending(self, manifest, operation):
        key = (manifest.scope, manifest.operation_id)
        if self.receipts[key].status != "NOT_SENT":
            return False
        self.receipts[key] = replace(self.receipts[key], status="SENT")
        return True

    async def record_receipt(self, manifest, status, receipt_ref=None):
        key = (manifest.scope, manifest.operation_id)
        self.receipts[key] = replace(self.receipts[key], status=status)
        return True


class Counter:
    def __init__(self):
        self.requests = []
        self.tokens = 20

    def measure(self, request, capacity):
        self.requests.append(request)
        return TokenMeasurement(self.tokens, (), "fake/1", True)


class Provider:
    descriptor = object()

    def __init__(self):
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return ProviderResult(
            request.contract_version,
            ProviderMessage("assistant", "ok"),
            ProviderUsage(1, 1, 0, 0, 0),
        )


def configured(user="user", session="session", operation="operation", stages=None):
    from efficiency_platform_agent.context.dispatch import ContextDispatch, DispatchPlan

    scope = ExecutionScope(
        ConversationScope(
            "tenant", user, "operations", "operations", "CONVERSATION", session
        ),
        "task",
        "execution",
        "root",
        "generate",
        "operations",
    )
    capacity = ModelCapacity(
        "deepseek",
        "fake",
        "test/1",
        1000,
        None,
        100,
        "conservative-utf8/1",
        "openai-chat/1",
        "NO_REASONING",
        True,
        "fake-only",
    )
    limits = WindowLimits(1000, None, 100, 10, 900)
    counter, store = Counter(), FakeStore()
    controller = ContextController(
        counter, store, b"unit-test-only-not-a-secret-key-000", clock=lambda: 1
    )

    class Authority:
        async def resolve(self, request, provider_id, model):
            assert (provider_id, model) == ("deepseek", "fake")
            return DispatchPlan(
                scope,
                ContextPolicy("node", "1", scope),
                (ContextPiece("input", scope, request.messages, required=True),),
                ContextMetadata(
                    "node",
                    "1",
                    "prompt/1",
                    "tools/1",
                    "schema/1",
                    1,
                    capacity,
                    limits,
                    request.options,
                ),
                ContextOperation(operation, 1, 100, True),
            )

    return (
        ContextDispatch(
            controller,
            store,
            Authority(),
            stage_store=stages,
            hmac_key=b"unit-test-only-not-a-secret-key-000",
        ),
        counter,
        store,
        scope,
    )


def request():
    return ProviderRequest(
        "provider-request/1",
        (
            ProviderMessage("system", "system"),
            ProviderMessage("user", "question"),
            ProviderMessage("developer", 'schema:{"type":"object"}'),
        ),
        JsonObject(
            (("max_tokens", 100), ("tools", (JsonObject((("type", "function"),)),)))
        ),
        1000,
    )


async def test_final_messages_tools_schema_are_counted_and_sent_unchanged():
    from efficiency_platform_agent.context.dispatch import ControlledModelProvider

    dispatch, counter, store, scope = configured()
    raw = Provider()
    provider = ControlledModelProvider(
        raw, dispatch, "deepseek", "fake", paid_transport=False
    )
    result = await provider.complete(request())
    assert result.message.content == "ok"
    assert raw.requests == [request()]
    assert counter.requests[-1] == raw.requests[0]
    assert store.receipts[(scope, "operation")].status == "SUCCEEDED"
    assert store.manifests[(scope, "operation")].output_schema_version == "schema/1"


async def test_required_overflow_never_reaches_provider():
    from efficiency_platform_agent.context.dispatch import ControlledModelProvider

    dispatch, counter, _, _ = configured()
    counter.tokens = 9999
    raw = Provider()
    with pytest.raises(ValueError, match="CONTEXT_REQUIRED_INPUT_TOO_LARGE"):
        await ControlledModelProvider(
            raw, dispatch, "deepseek", "fake", paid_transport=False
        ).complete(request())
    assert raw.requests == []


async def test_successful_operation_is_not_sent_twice():
    from efficiency_platform_agent.context.dispatch import ControlledModelProvider

    dispatch, _, _, _ = configured()
    raw = Provider()
    provider = ControlledModelProvider(
        raw, dispatch, "deepseek", "fake", paid_transport=False
    )
    await provider.complete(request())
    with pytest.raises(ValueError, match="CONTEXT_OPERATION_BLOCKED"):
        await provider.complete(request())
    assert len(raw.requests) == 1


async def test_paid_provider_cannot_skip_post_reservation_gate():
    from efficiency_platform_agent.context.dispatch import ControlledModelProvider

    dispatch, _, store, scope = configured()
    with pytest.raises(ValueError, match="CONTEXT_TRANSPORT_GATE_REQUIRED"):
        await ControlledModelProvider(
            Provider(), dispatch, "deepseek", "fake", paid_transport=True
        ).complete(request())
    assert store.receipts[(scope, "operation")].status == "NOT_SENT"


async def test_trusted_stage_entry_keeps_repair_input_and_context_isolated():
    from efficiency_platform_agent.context.stages import stage_entry
    from efficiency_platform_agent.core.context_dispatch import current_model_stage

    observed = []

    @stage_entry("intent", inputs=("text",))
    async def run(text):
        stage = current_model_stage()
        observed.append((stage.stage_id, stage.semantic_input))
        return stage

    first = await run("original")
    second = await run("changed")
    assert first.stage_id == second.stage_id
    assert first.semantic_input != second.semantic_input
    assert current_model_stage() is None


class FakeStages:
    def __init__(self):
        self.rows = {}

    async def claim(self, scope, stage_id, semantic_hash, deadline):
        from efficiency_platform_agent.core.context_stage import StageSlot

        key = scope, stage_id
        if key not in self.rows:
            self.rows[key] = [semantic_hash, deadline, 1, "CLAIMED"]
        row = self.rows[key]
        if row[:2] != [semantic_hash, deadline]:
            raise ValueError("CONTEXT_STAGE_CONFLICT_409")
        if row[3] == "INVALID" and row[2] < 3:
            row[2] += 1
            row[3] = "CLAIMED"
        if row[3] != "CLAIMED":
            raise ValueError("CONTEXT_STAGE_BLOCKED")
        from hashlib import sha256

        return StageSlot(row[2], f"{sha256(stage_id.encode()).hexdigest()}-{row[2]}")

    async def transition(self, scope, stage_id, slot, expected, status):
        row = self.rows[scope, stage_id]
        if row[2:] != [slot, expected]:
            return False
        row[3] = status
        return True


async def test_validated_repair_uses_next_fixed_slot_with_original_semantics():
    from efficiency_platform_agent.context.dispatch import ControlledModelProvider
    from efficiency_platform_agent.core.context_dispatch import (
        allow_context_repair,
        model_stage,
    )

    stages = FakeStages()
    dispatch, _, store, scope = configured(stages=stages)
    raw = Provider()
    provider = ControlledModelProvider(
        raw, dispatch, "deepseek", "fake", paid_transport=False
    )
    with model_stage("operation", b"original") as stage:
        await provider.complete(request())
        assert stages.rows[scope, "operation"][3] == "RETURNED"
        await allow_context_repair()
        repair = replace(
            request(),
            messages=request().messages
            + (ProviderMessage("developer", "repair schema"),),
        )
        await provider.complete(repair)
        await stage.complete()
    assert [r.messages for r in raw.requests] == [request().messages, repair.messages]
    assert {key[1][-2:] for key in store.receipts} == {"-1", "-2"}
    assert stages.rows[scope, "operation"][2:] == [2, "SUCCEEDED"]
    with (
        model_stage("operation", b"changed"),
        pytest.raises(ValueError, match="CONTEXT_STAGE_CONFLICT_409"),
    ):
        await provider.complete(request())


async def test_unvalidated_return_cannot_allocate_new_slot():
    from efficiency_platform_agent.context.dispatch import ControlledModelProvider
    from efficiency_platform_agent.core.context_dispatch import model_stage

    dispatch, _, _, _ = configured(stages=FakeStages())
    raw = Provider()
    provider = ControlledModelProvider(
        raw, dispatch, "deepseek", "fake", paid_transport=False
    )
    with model_stage("operation", b"original"):
        await provider.complete(request())
        with pytest.raises(ValueError, match="CONTEXT_STAGE_BLOCKED"):
            await provider.complete(request())
    assert len(raw.requests) == 1


def test_actual_factory_requires_dispatch_when_enabled():
    from pydantic import SecretStr

    from efficiency_platform_agent.harness.local_real_factory import (
        build_local_agent_application,
    )
    from tests.unit.harness.test_local_real_factory import synthetic_settings

    settings = synthetic_settings().model_copy(
        update={
            "context_enabled": True,
            "context_internal_secret": SecretStr("fake-internal-secret-01234567890123"),
            "context_hmac_key": SecretStr("fake-hmac-key-01234567890123456789"),
        }
    )
    with pytest.raises(ValueError, match="CONTEXT_DISPATCH_REQUIRED"):
        build_local_agent_application(settings, provider=Provider(), test_mode=True)


class BusinessHarness:
    """仅测试使用的显式Fake发布资产和结果，实际运行Controller与ModelRuntime。"""

    def __init__(self, outputs, domain="operations"):
        from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
        from efficiency_platform_agent.context.dispatch import (
            ContextDispatch,
            ControlledModelProvider,
            DispatchPlan,
        )
        from efficiency_platform_agent.core.context_dispatch import current_model_stage
        from efficiency_platform_agent.core.model import ModelCandidate, ModelTier
        from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
        from efficiency_platform_agent.providers.llm.registry import (
            ModelProviderRegistry,
        )
        from efficiency_platform_agent.routing.model_router import ModelPolicyRouter

        self.counter, self.store, self.stages = Counter(), FakeStore(), FakeStages()
        self.scope = ExecutionScope(
            ConversationScope(
                "tenant", "user", domain, domain, "CONVERSATION", "session"
            ),
            "task",
            "execution",
            "root",
            "generate",
            domain,
        )
        self.requests = []
        harness = self

        class Recording(FakeModelProvider):
            async def complete(self, request):
                harness.requests.append(request)
                return await super().complete(request)

        self.raw = Recording(
            "fake",
            [
                ProviderResult(
                    "provider-result/1",
                    message
                    if isinstance(message, ProviderMessage)
                    else ProviderMessage("assistant", message),
                    ProviderUsage(1, 1, 0, 0, 0),
                )
                for message in outputs
            ],
        )

        class FakeAuthority:
            async def resolve(self, request, provider_id, model):
                stage = current_model_stage()
                assert stage is not None
                scope = replace(harness.scope, subtask_id=stage.node_id)
                capacity = ModelCapacity(
                    "deepseek",
                    model,
                    "fake/1",
                    1000000,
                    None,
                    100000,
                    "conservative-utf8/1",
                    "openai-chat/1",
                    "NO_REASONING",
                    True,
                    "offline-fake-only",
                )
                output = dict(request.options.items).get("max_tokens", 100)
                limits = WindowLimits(1000000, None, output, 100, 900000)
                return DispatchPlan(
                    scope,
                    ContextPolicy(stage.node_id, "1", scope),
                    (ContextPiece("final", scope, request.messages, required=True),),
                    ContextMetadata(
                        stage.node_id,
                        "1",
                        "prompt/1",
                        "tools/1",
                        "schema/1",
                        1,
                        capacity,
                        limits,
                        request.options,
                    ),
                    ContextOperation(stage.stage_id, 1, 10000, True),
                )

        self.dispatch = ContextDispatch(
            ContextController(
                self.counter,
                self.store,
                b"unit-test-only-not-a-secret-key-000",
                clock=lambda: 1,
            ),
            self.store,
            FakeAuthority(),
            stage_store=self.stages,
            hmac_key=b"unit-test-only-not-a-secret-key-000",
        )
        self.provider = ControlledModelProvider(
            self.raw, self.dispatch, "deepseek", "fake", paid_transport=False
        )
        registry = ModelProviderRegistry()
        registry.register("fake", self.provider)
        self.runtime = ModelRuntime(
            ModelPolicyRouter(
                [
                    ModelCandidate(
                        f"fake-{tier.value}",
                        "fake",
                        "fake",
                        tier,
                        True,
                        True,
                        1000000,
                        True,
                        False,
                    )
                    for tier in ModelTier
                ]
            ),
            registry,
        )

    def assert_controlled(self, count):
        assert len(self.requests) == count
        assert len(self.store.manifests) == count
        assert all(request in self.counter.requests for request in self.requests)
        assert all(row.status == "SUCCEEDED" for row in self.store.receipts.values())


async def test_hr_real_service_validates_repairs_and_replays_without_new_send():
    from efficiency_platform_agent.agents.hr.service import HrSkillService
    from efficiency_platform_agent.contracts.hr import EvaluationOutput, HrSkillRequest
    from efficiency_platform_agent.core.execution_control import RunControl
    from tests.unit.agents.hr.test_hr_service import FakeAssembler

    harness = BusinessHarness(
        [
            "{}",
            '{"assessments":[{"requirement_id":"a","status":"MATCH","reason":"明确","evidence":[{"block_id":"b","start":0,"end":6,"quote":"Python"}]}]}',
        ],
        "hr",
    )
    service = HrSkillService(FakeAssembler(EvaluationOutput), harness.provider)
    control = RunControl()
    value = HrSkillRequest(
        run_id="r",
        operation_id="o",
        blocks=[{"block_id": "b", "text": "Python"}],
        requirements=[{"requirement_id": "a", "criterion": "Python"}],
    )
    result = await service.execute("hr.requirements.evaluate", value, control)
    assert result == await service.execute("hr.requirements.evaluate", value, control)
    harness.assert_controlled(2)
    assert len(harness.requests[1].messages) == len(harness.requests[0].messages) + 1
    assert "memory_context" not in str(harness.requests)
    assert [row[2:] for row in harness.stages.rows.values()] == [[2, "SUCCEEDED"]]


async def test_customer_gateway_final_schema_and_repair_are_controlled():
    from pydantic import BaseModel

    from efficiency_platform_agent.agents.customer_service.model_gateway import (
        ReleaseStructuredModelGateway,
    )
    from tests.unit.agents.customer_service.test_evidence_pack import bundle

    class Output(BaseModel):
        answer: str

    config = bundle()
    config.model_policy = config.model_policy.model_copy(update={"max_retries": 2})
    harness = BusinessHarness(["{}", '{"answer":"ok"}'], "customer-service")
    gateway = ReleaseStructuredModelGateway(harness.provider, config)
    assert (
        await gateway.complete("sufficiency", {"question": "test"}, Output)
    ).answer == "ok"
    assert (
        await gateway.complete("sufficiency", {"question": "test"}, Output)
    ).answer == "ok"
    harness.assert_controlled(2)
    assert "json_schema" in dict(harness.requests[1].options.items)
    assert harness.requests[1].messages[-1].role == "developer"


async def test_intent_model_runtime_first_and_repair_are_controlled():
    import json

    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )
    from tests.orchestration.test_intent_interpreter import _complete_intent

    harness = BusinessHarness(["{}", json.dumps(_complete_intent())])
    await IntentInterpreter(harness.runtime).interpret(
        "做运营方案", ConversationContext()
    )
    harness.assert_controlled(2)
    assert [row[2:] for row in harness.stages.rows.values()] == [[2, "SUCCEEDED"]]


async def test_scenario_final_prompt_and_repair_are_controlled():
    import json

    from efficiency_platform_agent.agents.operation.specialists.scenario_model_executor import (
        ScenarioModelExecutor,
    )
    from tests.unit.agents.operation.specialists.test_scenario_model_executor import (
        _Assembler,
        _brand_payload,
    )

    harness = BusinessHarness(["{}", json.dumps(_brand_payload(), ensure_ascii=False)])
    await ScenarioModelExecutor(harness.runtime, _Assembler()).generate_with_usage(
        run_id="run",
        scenario="brand_operation_plan",
        stage="plan",
        platform=None,
        user_request="品牌方案",
        input_artifact_ids=(),
        evidence=None,
    )
    harness.assert_controlled(2)


async def test_research_tool_loop_every_final_request_is_controlled():
    from efficiency_platform_agent.orchestration.research_v2.tool_loop import (
        ResearchToolLoop,
    )
    from tests.orchestration.research_v2.test_tool_loop import (
        _Assembler,
        _budget,
        _call,
        _Executor,
        _pack,
        _reflection,
        _request,
        _success,
    )

    harness = BusinessHarness(
        [
            ProviderMessage("assistant", None, tool_calls=(_call(),)),
            _pack(),
            _reflection(),
        ]
    )
    await ResearchToolLoop(
        harness.runtime, _Assembler(), _Executor({"call-1": _success()})
    ).execute(_request(), frozenset({"research.discover.v2"}), _budget())
    harness.assert_controlled(3)
    assert "tools" in dict(harness.requests[0].options.items)
    assert "json_schema" in dict(harness.requests[1].options.items)


async def test_model_backed_specialist_schema_repair_uses_same_stage():
    import json

    from tests.unit.agents.operation.specialists.test_model_backed_v2 import (
        draft,
        specialist,
        task,
    )

    valid = draft()
    invalid = dict(valid, title=123)
    harness = BusinessHarness([json.dumps(invalid), json.dumps(valid)])
    await specialist(harness.runtime).run(task())
    harness.assert_controlled(2)
    assert [row[2:] for row in harness.stages.rows.values()] == [[2, "SUCCEEDED"]]


async def test_actual_factory_installs_gate_for_intent_and_direct():
    from pydantic import SecretStr

    from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
    from efficiency_platform_agent.core.enums import RunStatus
    from efficiency_platform_agent.harness.local_real_factory import (
        build_local_agent_application,
    )
    from tests.api.test_conversation_routes import intent
    from tests.unit.harness.test_local_real_factory import synthetic_settings

    parsed = intent().model_copy(update={"task_type": "general_chat"})
    harness = BusinessHarness([parsed.model_dump_json(), "品牌定位说明"])
    settings = synthetic_settings().model_copy(
        update={
            "context_enabled": True,
            "context_internal_secret": SecretStr("fake-internal-secret-01234567890123"),
            "context_hmac_key": SecretStr("unit-test-only-not-a-secret-key-000"),
        }
    )
    application = build_local_agent_application(
        settings,
        provider=harness.raw,
        test_mode=True,
        context_dispatch=harness.dispatch,
    )
    try:
        submitted = await application.conversation.submit(
            "session",
            "tenant",
            ConversationMessageV1(
                message="解释品牌定位", request_id="request", user_id="user"
            ),
        )
        await application.runtime.wait_for_background_tasks()
        result = await application.runtime.get_run(submitted.run_id, "tenant")
        assert result.status is RunStatus.SUCCEEDED
        harness.assert_controlled(2)
        assert {manifest.node_id for manifest in harness.store.manifests.values()} == {
            "intent",
            "direct",
        }
    finally:
        await application.close()


@pytest.mark.parametrize("complete", [True, False])
async def test_stream_counts_final_request_and_truncation_is_not_repairable(complete):
    from efficiency_platform_agent.context.dispatch import (
        ControlledStreamingModelProvider,
    )
    from efficiency_platform_agent.core.context_dispatch import (
        allow_context_repair,
        model_stage,
    )
    from efficiency_platform_agent.core.run import ProviderStreamChunk

    class Streaming(Provider):
        async def stream(self, request):
            self.requests.append(request)
            yield ProviderStreamChunk(delta="one")
            if complete:
                yield ProviderStreamChunk(delta="two", finish_reason="stop")

    dispatch, counter, store, _scope = configured(stages=FakeStages())
    raw = Streaming()
    provider = ControlledStreamingModelProvider(
        raw, dispatch, "deepseek", "fake", paid_transport=False
    )
    with model_stage("operation", b"original"):
        chunks = [chunk async for chunk in provider.stream(request())]
        assert chunks[0].delta == "one"
        if not complete:
            with pytest.raises(ValueError, match="CONTEXT_STAGE_REPAIR_FORBIDDEN"):
                await allow_context_repair()
    assert len(raw.requests) == 1
    assert counter.requests[-1] == raw.requests[0]
    assert next(iter(store.receipts.values())).status == (
        "SUCCEEDED" if complete else "UNKNOWN"
    )


async def test_stream_closed_after_finish_chunk_remains_unknown_until_exhausted():
    from efficiency_platform_agent.context.dispatch import (
        ControlledStreamingModelProvider,
    )
    from efficiency_platform_agent.core.run import ProviderStreamChunk

    class Streaming(Provider):
        async def stream(self, request):
            yield ProviderStreamChunk(delta="one", finish_reason="stop")
            yield ProviderStreamChunk()

    dispatch, _, store, _ = configured()
    iterator = ControlledStreamingModelProvider(
        Streaming(), dispatch, "deepseek", "fake", paid_transport=False
    ).stream(request())
    await anext(iterator)
    await iterator.aclose()
    assert next(iter(store.receipts.values())).status == "UNKNOWN"


async def test_wire_mutation_is_blocked_before_fake_http_send():
    from efficiency_platform_agent.context.dispatch import ControlledModelProvider
    from efficiency_platform_agent.core.context_dispatch import (
        current_context_send_guard,
    )

    calls = []

    class Wire(Provider):
        async def complete(self, value):
            await current_context_send_guard().before_send(
                {
                    "model": "fake",
                    "messages": [{"role": "user", "content": "changed"}],
                    "max_tokens": 100,
                }
            )
            calls.append(value)
            return await super().complete(value)

    dispatch, _, _, _ = configured()
    with pytest.raises(ValueError, match="CONTEXT_WIRE_REQUEST_CHANGED"):
        await ControlledModelProvider(
            Wire(), dispatch, "deepseek", "fake", paid_transport=True
        ).complete(request())
    assert calls == []


async def test_paid_transport_reserves_then_finalizes_before_mock_wire():
    import json
    import time
    from types import SimpleNamespace

    import httpx

    from efficiency_platform_agent.context.dispatch import ControlledModelProvider
    from efficiency_platform_agent.providers.deepseek_stream import (
        DeepSeekStreamingProvider,
    )
    from efficiency_platform_agent.providers.paid_http import PaidHttpTransport

    events = []

    class FakeLedger:
        def active_budget_id(self):
            return "offline"

        def reserve(self, *args, **kwargs):
            events.append("reserve")
            return SimpleNamespace(
                reservation_id="offline",
                deadline_epoch_ms=int(time.time() * 1000) + 10000,
            )

        def record_status(self, *args):
            pass

        def check_live(self, *args):
            pass

        def finish(self, *args):
            pass

        def settle(self, *args):
            pass

    dispatch, counter, store, scope = configured()

    async def upstream(wire):
        assert events == ["reserve"]
        assert store.receipts[scope, "operation"].status == "SENT"
        assert counter.requests[-1] == request()
        payload = json.loads(wire.content)
        assert payload["messages"][-1]["content"].startswith("[DEVELOPER INSTRUCTION]")
        events.append("http")
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text='data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1}}\n\ndata: [DONE]\n\n',
        )

    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            FakeLedger(),
            httpx.MockTransport(upstream),
            "deepseek",
            require_context_guard=True,
        )
    ) as client:
        raw = DeepSeekStreamingProvider(
            client, "fake", api_key="offline-test", base_url="https://offline.invalid"
        )
        result = await ControlledModelProvider(
            raw, dispatch, "deepseek", "fake", paid_transport=True
        ).complete(request())
    assert result.error is None
    assert events == ["reserve", "http"]
    assert store.receipts[scope, "operation"].status == "SUCCEEDED"


async def test_concurrent_users_and_sessions_have_distinct_manifests_and_hmacs():
    import asyncio

    from efficiency_platform_agent.context.dispatch import ControlledModelProvider

    shared = FakeStore()

    async def invoke(user, session):
        dispatch, counter, _, scope = configured(user=user, session=session)
        dispatch.store = shared
        dispatch.controller = ContextController(
            counter, shared, b"unit-test-only-not-a-secret-key-000", clock=lambda: 1
        )
        await ControlledModelProvider(
            Provider(), dispatch, "deepseek", "fake", paid_transport=False
        ).complete(request())
        return scope

    scopes = await asyncio.gather(
        invoke("u1", "s1"), invoke("u2", "s1"), invoke("u1", "s2")
    )
    assert {m.scope for m in shared.manifests.values()} == set(scopes)
    assert len({m.canonical_request_hmac for m in shared.manifests.values()}) == 3


async def test_intent_planning_agent_repair_uses_original_stage_and_final_schema():
    from efficiency_platform_agent.orchestration.intent_v2.interpreter import (
        OperationIntentPlanningAgent,
    )
    from tests.orchestration.intent_v2.test_operation_planner import (
        _Assembler,
        _budget,
        _plan,
    )

    harness = BusinessHarness(["{}", _plan("brand_operation_plan")])
    plan = await OperationIntentPlanningAgent(harness.runtime, _Assembler()).plan(
        run_id="run",
        user_text="品牌规划",
        visible_history=(),
        remaining_budget=_budget(),
    )
    assert plan.primary_scenario == "brand_operation_plan"
    harness.assert_controlled(2)
    assert [row[2:] for row in harness.stages.rows.values()] == [[2, "SUCCEEDED"]]


async def test_customer_gateway_stream_uses_controller_and_validates_complete_json():
    from pydantic import BaseModel

    from efficiency_platform_agent.agents.customer_service.model_gateway import (
        ReleaseStructuredModelGateway,
    )
    from efficiency_platform_agent.context.dispatch import (
        ControlledStreamingModelProvider,
    )
    from efficiency_platform_agent.core.run import ProviderStreamChunk
    from tests.unit.agents.customer_service.test_evidence_pack import bundle

    class Output(BaseModel):
        answer: str

    harness = BusinessHarness([], "customer-service")

    class Streaming(Provider):
        async def stream(self, request):
            harness.requests.append(request)
            yield ProviderStreamChunk(delta='{"answer":')
            yield ProviderStreamChunk(delta='"ok"}', finish_reason="stop")

    gateway = ReleaseStructuredModelGateway(
        ControlledStreamingModelProvider(
            Streaming(), harness.dispatch, "deepseek", "fake", paid_transport=False
        ),
        bundle(),
    )
    contents = []
    value = await gateway.stream_complete(
        "sufficiency", {"question": "test"}, Output, contents.append
    )
    assert value.answer == "ok"
    assert contents[-1] == '{"answer":"ok"}'
    harness.assert_controlled(1)
    assert [row[2:] for row in harness.stages.rows.values()] == [[1, "SUCCEEDED"]]


async def test_research_explicit_supplement_recounts_the_second_synthesis():
    from efficiency_platform_agent.orchestration.research_v2.tool_loop import (
        ResearchToolLoop,
    )
    from tests.orchestration.research_v2.test_tool_loop import (
        _Assembler,
        _budget,
        _call,
        _Executor,
        _pack,
        _request,
        _success,
    )

    harness = BusinessHarness(
        [
            ProviderMessage("assistant", None, tool_calls=(_call(),)),
            _pack(),
            ProviderMessage(
                "assistant", None, tool_calls=(_call("call-2", query="more"),)
            ),
            _pack(sources=("1", "2")),
        ]
    )
    result = await ResearchToolLoop(
        harness.runtime,
        _Assembler(),
        _Executor({"call-1": _success(), "call-2": _success("call-2", suffix="2")}),
    ).execute(_request(), frozenset({"research.discover.v2"}), _budget())
    assert len(result.sources) == 2
    harness.assert_controlled(4)
    syntheses = [
        m
        for m in harness.store.manifests.values()
        if m.node_id == "research-synthesize"
    ]
    assert len(syntheses) == 2
    assert syntheses[0].operation_id != syntheses[1].operation_id


async def test_repair_cannot_refresh_original_stage_publication():
    from efficiency_platform_agent.context.dispatch import ControlledModelProvider
    from efficiency_platform_agent.core.context_dispatch import (
        allow_context_repair,
        model_stage,
    )

    dispatch, _, _, _ = configured(stages=FakeStages())
    original = dispatch.authority

    class ChangedPublication:
        async def resolve(self, *args):
            plan = await original.resolve(*args)
            return replace(
                plan,
                policy=replace(plan.policy, version="2"),
                metadata=replace(plan.metadata, policy_version="2"),
            )

    raw = Provider()
    provider = ControlledModelProvider(
        raw, dispatch, "deepseek", "fake", paid_transport=False
    )
    with model_stage("operation", b"original"):
        await provider.complete(request())
        await allow_context_repair()
        dispatch.authority = ChangedPublication()
        with pytest.raises(ValueError, match="CONTEXT_STAGE_CONFLICT_409"):
            await provider.complete(request())
    assert len(raw.requests) == 1


@pytest.mark.parametrize("version,expected", [(1, 2000), (2, 700)])
async def test_intent_sends_explicit_output_bound_through_real_paid_transport(
    version, expected
):
    import json
    import time
    from types import SimpleNamespace

    import httpx

    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )
    from efficiency_platform_agent.providers.deepseek_stream import (
        DeepSeekStreamingProvider,
    )
    from efficiency_platform_agent.providers.paid_http import PaidHttpTransport
    from tests.orchestration.intent_v2.test_interpreter import (
        VALID_PATCH,
        _budget,
        _execute,
        _interpreter,
    )
    from tests.orchestration.test_intent_interpreter import _complete_intent

    class Book:
        def active_budget_id(self):
            return "offline"

        def reserve(self, *args, **kwargs):
            return SimpleNamespace(
                reservation_id="offline",
                deadline_epoch_ms=int(time.time() * 1000) + 10000,
            )

        def record_status(self, *args):
            pass

        def check_live(self, *args):
            pass

        def finish(self, *args):
            pass

        def settle(self, *args):
            pass

    wires = []
    output = json.dumps(_complete_intent()) if version == 1 else VALID_PATCH

    def upstream(request):
        wires.append(json.loads(request.content))
        event = {
            "choices": [{"delta": {"content": output}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text="data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n",
        )

    harness = BusinessHarness([])
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            Book(),
            httpx.MockTransport(upstream),
            "deepseek",
            require_context_guard=True,
        )
    ) as client:
        harness.provider.inner = DeepSeekStreamingProvider(
            client,
            "fake",
            api_key="offline-test",
            base_url="https://offline.invalid",
            max_retries=0,
        )
        harness.provider.paid_transport = True
        if version == 1:
            await IntentInterpreter(harness.runtime).interpret(
                "做运营方案", ConversationContext()
            )
        else:
            interpreter, _, _, _ = _interpreter(
                (), budgets=(_budget(output_tokens=700),)
            )
            interpreter.model_runtime = harness.runtime
            await _execute(interpreter)
    assert len(wires) == 1
    assert wires[0]["max_tokens"] == expected
    assert all(
        receipt.status == "SUCCEEDED" for receipt in harness.store.receipts.values()
    )


async def test_server_published_schema_variants_allow_only_bounded_real_runtime_repair():
    import time

    from efficiency_platform_agent.context.stages import stage_entry
    from efficiency_platform_agent.core.budget import RemainingBudget
    from efficiency_platform_agent.core.context_dispatch import allow_context_repair
    from efficiency_platform_agent.core.model import ModelDemand, ModelTier
    from efficiency_platform_agent.core.run_context_binding import (
        RunContextBinding,
        bind_run_context,
    )
    from efficiency_platform_agent.harness.context_authority import (
        ServerDispatchAuthority,
    )

    harness = BusinessHarness(["{}", '{"ok":true}'])
    capacity = ModelCapacity(
        "deepseek",
        "fake",
        "offline/1",
        1000000,
        None,
        100,
        "conservative-utf8/1",
        "openai-chat/1",
        "NO_REASONING",
        True,
        "offline-only",
    )
    limits = WindowLimits(1000000, None, 100, 100, 900000)

    def options(schema, tokens=100):
        return JsonObject(
            (
                ("max_tokens", tokens),
                ("json_schema", JsonObject((("title", schema), ("type", "object")))),
                ("logical_model", "fake"),
            )
        )

    first = ContextMetadata(
        "server-repair",
        "release/1",
        "prompt/1",
        "tools/1",
        "schema/1",
        1,
        capacity,
        limits,
        options("first"),
    )
    second = replace(first, output_schema_version="schema/2", options=options("second"))
    harness.dispatch.authority = ServerDispatchAuthority(
        {("deepseek", "fake", "server-repair"): (first, second)},
        {"server-repair": ("operations", "generate")},
    )
    harness.dispatch.authority.assert_ready()
    remaining = RemainingBudget(3, 0, 10000, 1000, 100000, 10000)
    demand = ModelDemand("test/1", ModelTier.BALANCED, True, False, 10, 100)

    @stage_entry("server-repair", inputs=("text",))
    async def execute(text):
        initial = await harness.runtime.complete(
            demand,
            ProviderRequest(
                "test/1", (ProviderMessage("user", text),), options("first"), 1000
            ),
            remaining_budget=remaining,
        )
        assert initial.result.message.content == "{}"
        await allow_context_repair()
        repaired = await harness.runtime.complete(
            demand,
            ProviderRequest(
                "test/1",
                (
                    ProviderMessage("user", text),
                    ProviderMessage("developer", "修复JSON"),
                ),
                options("second", 50),
                1000,
            ),
            remaining_budget=remaining,
        )
        assert repaired.result.message.content == '{"ok":true}'

    with bind_run_context(
        RunContextBinding(
            harness.scope.conversation, "task", "execution", int(time.time()) + 100
        )
    ):
        await execute("original")
    harness.assert_controlled(2)
    assert {
        manifest.output_schema_version for manifest in harness.store.manifests.values()
    } == {"schema/1", "schema/2"}
    assert {
        manifest.output_reserve_tokens for manifest in harness.store.manifests.values()
    } == {100}
    assert dict(harness.requests[1].options.items)["max_tokens"] == 50


async def test_debug_http_bearer_task_scope_reaches_real_gateway_and_controller():
    from types import SimpleNamespace

    import httpx
    from fastapi import FastAPI
    from pydantic import BaseModel

    from efficiency_platform_agent.agents.customer_service.model_gateway import (
        ReleaseStructuredModelGateway,
        _freeze,
    )
    from efficiency_platform_agent.agents.customer_service.service import (
        CustomerServiceRunService,
    )
    from efficiency_platform_agent.api.customer_service_routes import (
        build_customer_service_router,
    )
    from efficiency_platform_agent.harness.context_authority import (
        ServerDispatchAuthority,
    )
    from efficiency_platform_agent.harness.hr_factory import internal_hr_authorizer
    from tests.api.test_customer_service_routes import RELEASE_ID, Graph
    from tests.unit.agents.customer_service.test_evidence_pack import bundle

    class Output(BaseModel):
        answer: str

    class Bundle(SimpleNamespace):
        def model_copy(self, *, update):
            return Bundle(**(vars(self) | update))

    config = Bundle(**vars(bundle()))

    class Releases:
        async def get(self, release_id):
            return config

    class DebugGraph(Graph):
        async def run(self, request, bundle, gateway):
            assert request.user_id == "debug-actor"
            assert request.history == ()
            assert (
                await gateway.complete(
                    "evidence_extract", {"question": request.message}, Output
                )
            ).answer == "ok"
            return await super().run(request, bundle, gateway)

    harness = BusinessHarness(['{"answer":"ok"}'], "customer-service")
    capacity = ModelCapacity(
        "deepseek",
        "fake",
        "offline/1",
        1000000,
        None,
        100,
        "conservative-utf8/1",
        "openai-chat/1",
        "NO_REASONING",
        True,
        "offline-only",
    )
    options = JsonObject(
        (
            ("logical_model", "main"),
            ("temperature", 0.0),
            ("top_p", 1.0),
            ("max_tokens", 100),
            ("response_format", JsonObject((("type", "json_object"),))),
            ("json_schema", _freeze(Output.model_json_schema())),
        )
    )
    node = "customer-service:evidence_extract"
    metadata = ContextMetadata(
        node,
        "release/1",
        "prompt/1",
        "tools/1",
        "schema/1",
        1,
        capacity,
        WindowLimits(1000000, None, 100, 100, 900000),
        options,
    )
    harness.dispatch.authority = ServerDispatchAuthority(
        {("deepseek", "fake", node): metadata}, {node: ("customer-service", "debug")}
    )
    service = CustomerServiceRunService(
        DebugGraph(),
        Releases(),
        lambda bundle: ReleaseStructuredModelGateway(harness.provider, bundle),
        context_required=True,
    )
    app = FastAPI()
    secret = "offline-internal-secret-01234567890"
    app.include_router(
        build_customer_service_router(service, internal_hr_authorizer(secret))
    )
    scope = {
        "tenant_id": "tenant",
        "user_id": "debug-actor",
        "domain": "customer-service",
        "top_level_agent_id": "customer-service",
        "session_kind": "TASK_ONLY",
        "session_id": None,
    }
    body = {
        "contract_version": "customer-service-rag-debug/1",
        "agent_key": "customer-service",
        "tenant_id": "tenant",
        "question": "test",
        "agent_release_id": str(RELEASE_ID),
        "agent_version_id": str(RELEASE_ID),
        "rag_policy_version_id": str(RELEASE_ID),
        "knowledge_bindings": [
            {"knowledge_base_id": str(RELEASE_ID), "index_release_id": str(RELEASE_ID)}
        ],
        "memory_context": {
            "schema_version": "memory-context/1",
            "memory_mode": "DISABLED",
            "scope": scope,
            "packet": None,
        },
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://offline"
    ) as client:
        response = await client.post(
            "/internal/v1/customer-service/rag-debug-runs",
            json=body,
            headers={"Authorization": "Bearer " + secret, "X-Tenant-ID": "tenant"},
        )
    assert response.status_code == 200, response.text
    harness.assert_controlled(1)
    manifest = next(iter(harness.store.manifests.values()))
    assert manifest.scope.task_id == response.json()["debug_run_id"]
    assert manifest.scope.execution_id == response.json()["debug_run_id"]
    assert manifest.scope.conversation.user_id == "debug-actor"
    assert manifest.scope.conversation.session_id is None
