"""真实Direct恢复、付费发送、RESULT、原Run保存与发布；模型仅MockTransport。"""

import asyncio
import json
import os
import re
import time
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from efficiency_platform_agent.agents.conversation.general_agent import (
    GeneralConversationAgent,
)
from efficiency_platform_agent.api.memory_routes import build_memory_router
from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
from efficiency_platform_agent.context.controller import ContextController
from efficiency_platform_agent.context.dispatch import (
    ContextDispatch,
    ControlledModelProvider,
)
from efficiency_platform_agent.contracts.direct_conversation import (
    DirectConversationSubmission,
)
from efficiency_platform_agent.contracts.requests import CreateRunRequestV1
from efficiency_platform_agent.contracts.responses import RunViewV1
from efficiency_platform_agent.core.budget import BudgetCharge, BudgetGuard, BudgetState
from efficiency_platform_agent.core.context_control import ModelCapacity, WindowLimits
from efficiency_platform_agent.core.context_ports import ContextMetadata
from efficiency_platform_agent.core.diagnostics import safe_exception_location
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.core.memory import ExecutionScope
from efficiency_platform_agent.core.memory_execution import (
    current_memory_result_checkpoint_permit,
)
from efficiency_platform_agent.core.memory_refresh import (
    MemoryContextResume,
    ResumeMode,
)
from efficiency_platform_agent.core.model import ModelCandidate, ModelTier
from efficiency_platform_agent.core.paid_budget import PaidBudgetPlan, PaidPriceLimit
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject, RunRequest
from efficiency_platform_agent.core.runtime import RunRecord, UsageSnapshot
from efficiency_platform_agent.harness.context_authority import ServerDispatchAuthority
from efficiency_platform_agent.harness.hr_factory import internal_hr_authorizer
from efficiency_platform_agent.harness.local_real_factory import (
    _SystemClock,
    _UuidGenerator,
)
from efficiency_platform_agent.harness.service import AgentRuntimeService
from efficiency_platform_agent.memory.context_refresh import MemoryContextRefreshService
from efficiency_platform_agent.memory.execution_authority import (
    MemorySendLeaseAuthority,
    StoredMemoryPacketValidator,
)
from efficiency_platform_agent.orchestration.builders.conversation_direct import (
    build_conversation_direct_registration,
)
from efficiency_platform_agent.orchestration.context_gate import (
    FencedModelProvider,
    MemoryDirectContextGate,
)
from efficiency_platform_agent.orchestration.contracts import GraphExecutionResult
from efficiency_platform_agent.orchestration.registry import GraphRegistry
from efficiency_platform_agent.orchestration.runtime import GraphRuntime
from efficiency_platform_agent.persistence.context_manifest import (
    MySqlContextManifestStore,
)
from efficiency_platform_agent.persistence.context_stage import MySqlContextStageStore
from efficiency_platform_agent.persistence.memory_context_refresh import (
    MySqlMemoryContextRefreshStore,
)
from efficiency_platform_agent.persistence.mysql_codec import _immutable_object
from efficiency_platform_agent.persistence.mysql_runtime import MySqlRunEventStore
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.providers.deepseek_stream import (
    DeepSeekStreamingProvider,
)
from efficiency_platform_agent.providers.llm.registry import ModelProviderRegistry
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)
from efficiency_platform_agent.providers.paid_http import PaidHttpTransport
from efficiency_platform_agent.routing.model_router import ModelPolicyRouter
from efficiency_platform_agent.routing.strategy_router import StrategyRouter
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)
from tests.integration.context_control.test_memory_stop_http import running
from tests.integration.memory.test_refresh_persistence import (
    refresh_case as refresh_case,  # noqa: PLC0414
)
from tests.integration.memory.test_refresh_run_metadata import (
    ops_case as ops_case,  # noqa: PLC0414
)

pytestmark = pytest.mark.skipif(
    os.environ.get("MEMORY_IT_ENABLED") != "1", reason="需root显式本机隔离双库"
)


def _safe_sql_diagnostic(error):
    facts = {"type": type(error).__name__, "project_frames": []}
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        for name in ("sqlstate", "pgcode"):
            value = getattr(error, name, None)
            if isinstance(value, str) and re.fullmatch(r"[A-Z0-9]{5}", value):
                facts["sqlstate"] = value
        args = getattr(error, "args", ())
        if (
            len(args) == 1
            and type(args[0]) is str
            and args[0]
            in {
                "CONTEXT_STAGE_WRITE_FAILED",
                "CONTEXT_STAGE_COMPLETION_FORBIDDEN",
                "CONTEXT_OPERATION_BLOCKED",
                "MEMORY_RESULT_UNAVAILABLE",
                "MEMORY_RESULT_CHECKPOINT_FORBIDDEN",
                "MEMORY_FROZEN_FRAME_CHANGED",
                "MEMORY_WAIT_CHECKPOINT_FORBIDDEN",
            }
        ):
            facts["fixed_code"] = args[0]
        if args and type(args[0]) is int and 0 <= args[0] <= 65535:
            facts["vendor_code"] = args[0]
        diag = getattr(error, "diag", None)
        for name in ("column_name", "datatype_name"):
            value = getattr(diag, name, None)
            if isinstance(value, str) and re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]{0,127}", value
            ):
                facts[name] = value
        frame = error.__traceback__
        while frame is not None:
            code = frame.tb_frame.f_code
            if "/src/efficiency_platform_agent/" in code.co_filename.replace("\\", "/"):
                facts["project_frames"].append(
                    (Path(code.co_filename).name, frame.tb_lineno, code.co_name)
                )
            frame = frame.tb_next
        error = getattr(error, "orig", None) or error.__cause__ or error.__context__
    facts["project_frames"] = facts["project_frames"][-8:]
    print("RF04_GRAPH_SQL_SAFE", json.dumps(facts), flush=True)


@pytest.mark.parametrize("refresh_case", ["graph-tenant"], indirect=True)
@pytest.mark.parametrize("expire_after_send", [False, True])
async def test_real_direct_http_resume_sends_once_and_publishes_after_run_save(
    ops_case, tmp_path, expire_after_send
):
    await _run_direct_case(ops_case, tmp_path, expire_after_send, False)


@pytest.mark.parametrize("refresh_case", ["graph-tenant"], indirect=True)
async def test_real_direct_reserved_ttl_keeps_original_graph_dispatch_frame(
    ops_case, tmp_path
):
    await _run_direct_case(ops_case, tmp_path, False, True)


@pytest.mark.parametrize("refresh_case", ["graph-tenant"], indirect=True)
@pytest.mark.parametrize(
    "failure",
    [
        "early_eof",
        "stop_after_capture",
        "source_after_capture",
    ],
)
async def test_real_direct_response_failures_never_publish_or_dispatch_twice(
    ops_case, tmp_path, failure
):
    await _run_direct_case(ops_case, tmp_path, False, False, failure=failure)


@pytest.mark.parametrize("refresh_case", ["graph-tenant"], indirect=True)
async def test_real_direct_original_deadline_after_result_never_publishes(
    ops_case, tmp_path
):
    await _run_direct_case(
        ops_case, tmp_path, False, False, failure="deadline_after_capture"
    )


@pytest.mark.parametrize("refresh_case", ["graph-tenant"], indirect=True)
@pytest.mark.parametrize(
    "publish_race",
    [
        "event_deadline",
        "hub_deadline",
        "stream_deadline",
        "stream_stop",
        "stream_source",
        "stream_stop_fallback",
    ],
)
async def test_real_result_scope_rechecks_each_sensitive_emit(
    ops_case, tmp_path, publish_race
):
    await _run_direct_case(ops_case, tmp_path, False, False, publish_race=publish_race)


async def _run_direct_case(
    ops_case,
    tmp_path,
    expire_after_send,
    reserve_then_expire,
    *,
    failure=None,
    publish_race=None,
):
    _, old, store, registry, _, repository, _, saver, index, _ = ops_case
    encode = saver.serializer.encode

    def observed_encode(location, value):
        try:
            return encode(location, value)
        except TypeError:
            channel = (
                location.coordinate[-1]
                if location.coordinate and location.coordinate[0] == "write"
                else "non-write"
            )
            safe_channel = (
                channel
                if re.fullmatch(r"[A-Za-z_:][A-Za-z0-9_:]{0,127}", channel)
                else "opaque"
            )
            print(
                "RF04_CHECKPOINT_TYPE_SAFE",
                json.dumps(
                    {"channel": safe_channel, "value_type": type(value).__name__}
                ),
                flush=True,
            )
            if isinstance(value, BaseException):
                _safe_sql_diagnostic(value)
            raise

    saver.serializer.encode = observed_encode
    registry.clock = time.time
    now = int(time.time())
    original_deadline = now + (
        14
        if failure == "deadline_after_capture"
        or publish_race is not None
        and "deadline" in publish_race
        else 60
    )
    packet = replace(
        old.context.packet,
        task_id=uuid4().hex,
        execution_id=uuid4().hex,
        issued_at=now,
        expires_at=now + 4,
    )
    context = replace(
        old.context,
        packet=packet,
        deadline_epoch_seconds=original_deadline,
        packet_digest=memory_packet_digest(packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(packet),
    )
    runtime_id, request_id = uuid4().hex, uuid4().hex
    record, _ = await store.claim(
        context, runtime_id, "OPERATIONS", "c" * 64, original_deadline
    )
    scope = ExecutionScope(
        packet.scope,
        packet.task_id,
        packet.execution_id,
        "direct",
        "assistant_response",
        "operations",
    )
    await registry.enroll(scope, runtime_id)
    run_request = RunRequest(
        request_id,
        packet.scope.tenant_id,
        packet.scope.user_id,
        "synthetic graph input",
        _immutable_object(
            {
                "context_scope": asdict(packet.scope),
                "memory_execution": context.metadata(),
                "context_request_fingerprint": record.request_fingerprint,
            }
        ),
    )
    budget = ExecutionBudget(3, 0, 40000, 2000, 60000, 100000)
    run = RunRecord(
        runtime_id,
        run_request,
        RunStatus.QUEUED,
        None,
        budget,
        BudgetState(BudgetCharge(), int(time.time() * 1000), original_deadline * 1000),
        UsageSnapshot(),
        1,
    )
    await repository.create(run)
    authority = MemorySendLeaseAuthority(registry, store)
    registry.install_result_authority(authority)
    manifests = MySqlContextManifestStore(store.engine, memory_execution_store=store)
    manifests.install_result_authority(authority)
    control = RunControl(timeout_ms=60000)
    if failure in {
        "stop_after_capture",
        "source_after_capture",
    }:

        async def after_complete_capture(point):
            if point != "after_result_commit":
                return
            if failure == "stop_after_capture":
                control.stop("AGENT_TASK_STOPPED")
            elif failure == "source_after_capture":
                from efficiency_platform_agent.core.memory_execution import (
                    MemoryInvalidation,
                )

                current = await store.get(
                    scope.conversation.tenant_id, scope.execution_id
                )
                await store.invalidate(
                    MemoryInvalidation(
                        scope.conversation.tenant_id,
                        scope.execution_id,
                        uuid4().hex,
                        current.execution_revision,
                        current.grant_epoch,
                        current.source_epoch + 1,
                        current.deletion_epoch,
                    )
                )

        manifests._result_fault_hook = after_complete_capture
    model, key = "rf04-graph-offline", b"rf04-graph-frozen-hmac-key-32-byte"
    options = JsonObject((("max_tokens", 2000), ("logical_model", model)))
    capacity = ModelCapacity(
        "deepseek",
        model,
        "rf04/1",
        64000,
        40000,
        2000,
        "conservative-utf8/1",
        "openai-chat/1",
        "NO_REASONING",
        True,
        "synthetic-only",
    )
    metadata = ContextMetadata(
        "direct",
        "rf04-window/1",
        "rf04-prompt/1",
        "none/1",
        "none/1",
        1,
        capacity,
        WindowLimits(64000, 40000, 2000, 100, 39800),
        options,
    )
    controller = ContextController(
        ConservativeRequestTokenCounter(),
        manifests,
        key,
        validator=StoredMemoryPacketValidator(store),
    )
    dispatch = ContextDispatch(
        controller,
        manifests,
        ServerDispatchAuthority(
            {("deepseek", model, "direct"): metadata},
            {"direct": ("operations", "assistant_response")},
            memory_execution_store=store,
        ),
        stage_store=MySqlContextStageStore(store.engine, key),
        hmac_key=key,
    )
    prepare = dispatch.prepare

    async def observed_prepare(*args, **kwargs):
        try:
            return await prepare(*args, **kwargs)
        except Exception as error:
            _safe_sql_diagnostic(error)
            raise

    dispatch.prepare = observed_prepare
    capture = manifests.capture_result_once

    async def observed_capture(*args, **kwargs):
        try:
            return await capture(*args, **kwargs)
        except Exception as error:
            _safe_sql_diagnostic(error)
            raise

    manifests.capture_result_once = observed_capture
    service = MemoryContextRefreshService(
        registry, MySqlMemoryContextRefreshStore(store)
    )
    registry.install_wait_authority(service)
    gate = MemoryDirectContextGate(
        service,
        store,
        registry,
        authority,
        saver=saver,
        checkpoint_store=index,
        dispatch=dispatch,
    )
    if failure == "deadline_after_capture":
        completed = gate.dispatch_completed

        async def complete_after_original_deadline(state, result):
            await completed(state, result)
            async with store.engine.connect() as connection:
                captured_count = (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM agent_memory_context_refresh WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='RESULT' AND phase='CAPTURED'"
                        ),
                        {
                            "tenant": scope.conversation.tenant_id.encode(),
                            "execution": scope.execution_id.encode(),
                        },
                    )
                ).scalar_one()
            assert captured_count == 1
            await asyncio.sleep(max(0, original_deadline - time.time()) + 0.1)
            assert time.time() >= record.deadline_epoch_seconds

        gate.dispatch_completed = complete_after_original_deadline
    valid_state, valid_writes = gate._valid_state, gate._valid_writes
    shape_count = [0]

    def budget_shape(value):
        if isinstance(value, BudgetState):
            value = asdict(value)
        if not isinstance(value, dict):
            return {"type": type(value).__name__}
        values = {
            key: value[key]
            for key in ("started_at_epoch_ms", "deadline_epoch_ms")
            if type(value.get(key)) is int
        }
        consumed = value.get("consumed", {})
        if isinstance(consumed, dict):
            values.update(
                {
                    key: number
                    for key, number in consumed.items()
                    if key
                    in {
                        "iterations",
                        "tool_calls",
                        "input_tokens",
                        "output_tokens",
                        "cost_microunits",
                    }
                    and type(number) is int
                }
            )
        return values

    def observed_state(values, **kwargs):
        accepted = valid_state(values, **kwargs)
        frame = kwargs.get("frame") or gate._current.get()
        if (
            frame is not None
            and frame.result is not None
            and shape_count[0] < 10
            and (not accepted or not kwargs.get("partial", False))
        ):
            expected = dict(frame.initial)
            if frame.submission is not None:
                expected["direct_submission"] = frame.submission
            expected.update(frame.result)
            facts = {
                "kind": "state",
                "accepted": accepted,
                "partial": kwargs.get("partial", False),
                "publish_checked": frame.publish_checked,
                "types": {key: type(value).__name__ for key, value in values.items()},
                "missing": sorted(set(expected) - set(values)),
                "extra": sorted(set(values) - set(expected)),
                "changed_raw": sorted(
                    key
                    for key in set(values) & set(expected)
                    if values[key] != expected[key]
                ),
                "budget_actual": budget_shape(values.get("budget_state")),
                "budget_original": budget_shape(frame.initial.get("budget_state")),
                "result_usage": {
                    key: value
                    for key, value in frame.result.get("usage", {}).items()
                    if type(value) is int
                },
            }
            print("RF04_CHECKPOINT_SHAPE_SAFE", json.dumps(facts), flush=True)
            shape_count[0] += 1
        return accepted

    def observed_writes(writes):
        accepted = valid_writes(writes)
        frame = gate._current.get()
        if frame is not None and frame.result is not None and shape_count[0] < 10:
            print(
                "RF04_CHECKPOINT_SHAPE_SAFE",
                json.dumps(
                    {
                        "kind": "writes",
                        "accepted": accepted,
                        "publish_checked": frame.publish_checked,
                        "types": [
                            (channel, type(value).__name__) for channel, value in writes
                        ],
                    }
                ),
                flush=True,
            )
            shape_count[0] += 1
        return accepted

    gate._valid_state, gate._valid_writes = observed_state, observed_writes
    service.frame_verifier, service.checkpoint_verifier = (
        gate.verify_wait_frame,
        gate.verify_wait_checkpoint,
    )
    begin_wait = service.begin_wait_intent

    async def observed_begin(scope_value, runtime, operation, attempt, phase, **kwargs):
        row = await registry._one(
            "SELECT wait_event_id,wait_phase,checkpoint_mode FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
            (scope_value.conversation.tenant_id, scope_value.execution_id),
        )
        print(
            "RF04_WAIT_PHASE_SAFE",
            json.dumps(
                {
                    "requested_phase": phase.value,
                    "existing_phase": None if row is None else row.get("wait_phase"),
                    "checkpoint_mode": None
                    if row is None
                    else row.get("checkpoint_mode"),
                    "existing_wait": bool(row and row.get("wait_event_id")),
                }
            ),
            flush=True,
        )
        return await begin_wait(
            scope_value, runtime, operation, attempt, phase, **kwargs
        )

    service.begin_wait_intent = observed_begin
    service.binding_updater, service.wait_task_resolver = (
        gate.update_wait_frame_binding,
        gate.wait_frame_task,
    )
    saver.install_context_checkpoint_authority(gate)
    index.install_context_checkpoint_authority(gate)
    dispatch.install_refresh(service, store)
    app, secret = FastAPI(), "rf04-synthetic-graph-internal-secret"

    @app.exception_handler(Exception)
    async def safe_error(_request, error):
        facts = {
            "code": "MEMORY_AUTHORITY_UNAVAILABLE",
            "error_type": type(error).__name__,
            "location": safe_exception_location(error),
        }
        print("RF04_GRAPH_HTTP_SAFE", json.dumps(facts), flush=True)
        return JSONResponse(status_code=503, content=facts)

    app.include_router(
        build_memory_router(
            store, internal_hr_authorizer(secret), None, refresh_service=service
        )
    )
    headers = {
        "Authorization": "Bearer " + secret,
        "X-Tenant-ID": packet.scope.tenant_id,
    }
    prefix = f"/internal/v1/memory/executions/{scope.execution_id}"
    book = SqlitePaidBudgetLedger(tmp_path / "graph-mock-budget.sqlite3")
    book.authorize(
        PaidBudgetPlan(
            "graph-offline",
            3,
            100,
            (now + 60) * 1000,
            3,
            100,
            60000,
            1,
            2,
            *([1000000] * 6),
        ),
        (
            PaidPriceLimit(
                "deepseek",
                model,
                100000,
                2000,
                10,
                "synthetic MockTransport only",
                "rf04/1",
                200000,
                1,
                0,
                1,
            ),
        ),
    )
    original_reserve = book.reserve
    reservations = []

    def reserve(*args, **kwargs):
        value = original_reserve(*args, **kwargs)
        reservations.append(value)
        if reserve_then_expire:
            time.sleep(4.1)
        return value

    book.reserve = reserve
    sends, receipts, publications = [], [], []
    data = [
        {"choices": [{"delta": {"content": "graph-response"}, "finish_reason": None}]},
        {
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "prompt_cache_hit_tokens": 0,
            },
        },
    ]
    wire = (
        "".join("data: " + json.dumps(value) + "\n\n" for value in data)
        + "data: [DONE]\n\n"
    ).encode()

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            if failure == "early_eof":
                yield ("data: " + json.dumps(data[0]) + "\n\n").encode()
                raise httpx.ReadError("synthetic incomplete stream")
            if expire_after_send:
                await asyncio.sleep(4.1)
            yield wire

        async def aclose(self):
            pass

    def upstream(request):
        sends.append(request)
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=Body()
        )

    class Diagnostics:
        def record(self, event):
            if event.error_code is not None:
                print(
                    "RF04_GRAPH_SAFE",
                    event.error_code,
                    event.error_type,
                    event.error_location,
                    flush=True,
                )

    async with (
        running(app) as internal,
        httpx.AsyncClient(
            transport=PaidHttpTransport(
                book,
                httpx.MockTransport(upstream),
                "deepseek",
                require_context_guard=True,
            )
        ) as client,
    ):
        raw = DeepSeekStreamingProvider(
            client,
            model,
            api_key="synthetic-only",
            base_url="https://offline.invalid",
            max_retries=0,
            logical_model_map={model: model},
        )
        provider = FencedModelProvider(
            ControlledModelProvider(
                raw, dispatch, "deepseek", model, paid_transport=True
            ),
            registry,
            "official",
            send_authority=authority,
        )
        providers = ModelProviderRegistry()
        providers.register("rf04-provider", provider)
        model_runtime = ModelRuntime(
            ModelPolicyRouter(
                (
                    ModelCandidate(
                        "rf04-balanced",
                        "rf04-provider",
                        model,
                        ModelTier.BALANCED,
                        False,
                        False,
                        64000,
                        True,
                        False,
                    ),
                )
            ),
            providers,
            diagnostic_recorder=Diagnostics(),
        )

        async def resolver(request, state):
            remaining = BudgetGuard().remaining(
                run.budget, run.budget_state, now_epoch_ms=int(time.time() * 1000)
            )
            if (
                failure == "deadline_after_capture"
                or publish_race is not None
                and "deadline" in publish_race
            ):
                remaining = replace(remaining, timeout_ms=5000)
            return DirectConversationSubmission(
                "direct-conversation/1",
                run_request,
                (),
                run_request.input_text,
                None,
                remaining,
            )

        graphs = GraphRegistry()
        graphs.register(
            build_conversation_direct_registration(
                GeneralConversationAgent(model_runtime),
                resolver,
                checkpointer=saver,
                memory_gate=gate,
            )
        )
        graph_runtime = GraphRuntime(
            graphs, checkpoint_store=index, diagnostic_recorder=Diagnostics()
        )
        graph_runtime.memory_registry = registry
        harness = AgentRuntimeService(
            repository=repository,
            event_store=MySqlRunEventStore(store.engine),
            router=StrategyRouter(frozenset({StrategyMode.DIRECT})),
            graph_runtime=graph_runtime,
            budget_guard=BudgetGuard(),
            budget=budget,
            clock=_SystemClock(),
            id_generator=_UuidGenerator(),
            memory_execution_store=store,
        )

        async def revoke_current_source():
            from efficiency_platform_agent.core.memory_execution import (
                MemoryInvalidation,
            )

            current = await store.get(scope.conversation.tenant_id, scope.execution_id)
            await store.invalidate(
                MemoryInvalidation(
                    scope.conversation.tenant_id,
                    scope.execution_id,
                    uuid4().hex,
                    current.execution_revision,
                    current.grant_epoch,
                    current.source_epoch + 1,
                    current.deletion_epoch,
                )
            )

        async def wait_original_deadline():
            assert current_memory_result_checkpoint_permit() is not None
            saved = await repository.get(runtime_id, scope.conversation.tenant_id)
            assert saved.status == RunStatus.SUCCEEDED
            assert time.time() < record.deadline_epoch_seconds
            print("RF04RACE_ENTERED_CURRENT_RESULT_SCOPE", flush=True)
            await asyncio.sleep(
                max(0, record.deadline_epoch_seconds - time.time()) + 0.1
            )

        if publish_race == "event_deadline":
            append = harness.event_store.append

            async def append_after_deadline(event):
                if event.event_type == "checkpoint_saved":
                    await wait_original_deadline()
                await append(event)

            harness.event_store.append = append_after_deadline
        if publish_race is not None and publish_race.startswith("stream_"):

            async def presentation(run_id, output):
                assert current_memory_result_checkpoint_permit() is not None
                yield "first-legitimate"
                if publish_race == "stream_deadline":
                    await wait_original_deadline()
                elif publish_race == "stream_source":
                    await revoke_current_source()
                else:
                    control.stop("AGENT_TASK_STOPPED")
                if publish_race == "stream_stop_fallback":
                    raise RuntimeError("synthetic presentation failure")
                yield "second-forbidden"

            harness.output_streamer = presentation
        lock_releases = []
        publish = harness.event_hub.publish_next

        async def observe(run_id, event, payload):
            current = await repository.get(run_id, scope.conversation.tenant_id)
            if event == "assistant_delta":
                assert (
                    current.status == RunStatus.SUCCEEDED
                    and current_memory_result_checkpoint_permit() is not None
                )
                if publish_race == "hub_deadline":
                    await harness.event_hub._lock.acquire()

                    async def release_after_deadline():
                        try:
                            await wait_original_deadline()
                        finally:
                            harness.event_hub._lock.release()

                    lock_releases.append(asyncio.create_task(release_after_deadline()))
            value = await publish(run_id, event, payload)
            if event == "assistant_delta":
                publications.append(event)
            return value

        harness.event_hub.publish_next = observe

        async def on_wait(wait_id, execution_id, emitted_runtime):
            assert (
                execution_id == scope.execution_id
                and emitted_runtime == runtime_id
                and not sends
            )
            response = await internal.get(prefix + "/wait", headers=headers)
            assert response.status_code == 200
            wait = await service.get_wait(scope.conversation, scope.execution_id)
            issued = int(time.time())
            candidate = replace(
                packet, packet_revision=2, issued_at=issued, expires_at=issued + 4
            )
            refreshed = replace(
                context, packet=candidate, packet_digest=memory_packet_digest(candidate)
            )
            command = MemoryContextResume(
                wait_id,
                1,
                1,
                uuid4().hex,
                record.request_fingerprint,
                ResumeMode.REFRESH,
                False,
                "memory-context-resume/2",
                wait.logical_operation_id,
                wait.canonical_request_hmac,
                1,
                wait.expected_current_context_fingerprint,
                refreshed,
            )
            body = asdict(command)
            body["refreshed_context"] = {
                "schema_version": "memory-context/1",
                "memory_mode": "EXACT_ONLY",
                "scope": asdict(scope.conversation),
                "packet": asdict(candidate),
                "authorization": {
                    key: value
                    for key, value in refreshed.metadata().items()
                    if key != "packet"
                },
            }
            body = json.loads(
                json.dumps(
                    body,
                    default=lambda value: (
                        sorted(value)
                        if isinstance(value, (set, frozenset))
                        else str(value)
                    ),
                )
            )
            resumed = await internal.post(
                prefix + "/resume", headers=headers, json=body
            )
            facts = (
                resumed.json()
                if resumed.headers.get("content-type", "").startswith(
                    "application/json"
                )
                else {}
            )
            assert resumed.status_code == 200, {
                "status": resumed.status_code,
                "code": facts.get("code"),
                "error_type": facts.get("error_type"),
                "location": facts.get("location"),
            }
            assert facts["dispatch_allowed"] is True
            receipts.append(facts)

        gate.on_wait = on_wait
        dispatch._on_wait = on_wait
        if not reserve_then_expire:
            await asyncio.sleep(4.1)
        request = CreateRunRequestV1(
            request_id=request_id,
            tenant_id=packet.scope.tenant_id,
            user_id=packet.scope.user_id,
            input_text=run_request.input_text,
            requested_strategy=StrategyMode.DIRECT,
        )
        with execution_scope(control):
            try:
                result = await asyncio.wait_for(
                    harness._execute_queued(run, request), 20
                )
            except Exception as error:  # noqa: BLE001 -- 仅保留类型与安全源码位置。
                if failure is not None:
                    result = None
                else:
                    raise AssertionError(
                        {
                            "type": type(error).__name__,
                            "location": safe_exception_location(error),
                        }
                    ) from None
        if lock_releases:
            await asyncio.gather(*lock_releases)
    if publish_race is not None:
        current = await repository.get(runtime_id, scope.conversation.tenant_id)
        assert current.status == RunStatus.SUCCEEDED
        events = await harness.event_hub.replay(runtime_id, 0)
        deltas = [
            event.payload["delta"]
            for event in events
            if event.event == "assistant_delta"
        ]
        assert deltas == (
            ["first-legitimate"] if publish_race.startswith("stream_") else []
        ), "LATE_RESULT_BODY_OR_FALLBACK_PUBLISHED"
        assert (
            len(sends)
            == len(reservations)
            == control.calls
            == book.snapshot()["calls"]
            == 1
        )
        assert book.snapshot()["inflight"] == 0
        async with store.engine.connect() as connection:
            captured = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM agent_memory_context_refresh WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='RESULT' AND phase='CAPTURED'"
                    ),
                    {
                        "tenant": scope.conversation.tenant_id.encode(),
                        "execution": scope.execution_id.encode(),
                    },
                )
            ).scalar_one()
            operation = (
                await connection.execute(
                    text(
                        "SELECT status FROM agent_context_operation WHERE tenant_id=:tenant AND execution_id=:execution"
                    ),
                    {
                        "tenant": scope.conversation.tenant_id.encode(),
                        "execution": scope.execution_id.encode(),
                    },
                )
            ).scalar_one()
        assert captured == 1 and operation == "SUCCEEDED"
        assert not await harness.can_emit_memory_events(
            runtime_id, scope.conversation.tenant_id
        )
        from efficiency_platform_agent.api.sse import stream_run_events

        stream = stream_run_events(
            harness.event_hub,
            runtime_id,
            can_emit=lambda: harness.can_emit_memory_events(
                runtime_id, scope.conversation.tenant_id
            ),
        )
        assert [part async for part in stream] == []
        return
    if failure is not None:
        assert not publications
        assert (
            len(sends)
            == len(reservations)
            == control.calls
            == book.snapshot()["calls"]
            == 1
        )
        assert book.snapshot()["inflight"] == 0
        current = await repository.get(runtime_id, scope.conversation.tenant_id)
        assert isinstance(result, RunViewV1)
        assert current.status in {
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
        }
        assert result.status == current.status.value
        assert (
            current.budget_state.deadline_epoch_ms == run.budget_state.deadline_epoch_ms
        )
        async with store.engine.connect() as connection:
            results = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM agent_memory_context_refresh WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='RESULT'"
                    ),
                    {
                        "tenant": scope.conversation.tenant_id.encode(),
                        "execution": scope.execution_id.encode(),
                    },
                )
            ).scalar_one()
            operation = (
                await connection.execute(
                    text(
                        "SELECT status FROM agent_context_operation WHERE tenant_id=:tenant AND execution_id=:execution"
                    ),
                    {
                        "tenant": scope.conversation.tenant_id.encode(),
                        "execution": scope.execution_id.encode(),
                    },
                )
            ).scalar_one()
        assert results == (0 if failure == "early_eof" else 1)
        assert operation == ("UNKNOWN" if failure == "early_eof" else "SUCCEEDED")
        if failure == "source_after_capture":
            current_execution = await store.get(
                scope.conversation.tenant_id, scope.execution_id
            )
            assert (
                current_execution.state == "REVOKED"
                and current_execution.source_epoch > context.packet.source_epoch
            )
        return
    if isinstance(result, GraphExecutionResult):
        pytest.fail(
            json.dumps(
                {
                    "code": result.failure.code
                    if result.failure
                    else "MEMORY_RESULT_CALLBACK_NOT_CALLED",
                    "status": result.next_status.value,
                    "sends": len(sends),
                    "attempts": control.calls,
                    "ledger_calls": book.snapshot()["calls"],
                }
            ),
            pytrace=False,
        )
    assert result.status == RunStatus.SUCCEEDED.value
    assert (
        len(sends)
        == len(receipts)
        == len(reservations)
        == control.calls
        == book.snapshot()["calls"]
        == 1
    )
    assert len(publications) == 1 and book.snapshot()["inflight"] == 0
    current = await repository.get(runtime_id, scope.conversation.tenant_id)
    assert (
        current.budget_state.started_at_epoch_ms == run.budget_state.started_at_epoch_ms
    )
    assert current.budget_state.deadline_epoch_ms == run.budget_state.deadline_epoch_ms
    assert (
        current.status == RunStatus.SUCCEEDED
        and dict(current.output.items)["content"] == "graph-response"
    )
    async with store.engine.connect() as connection:
        rows = (
            (
                await connection.execute(
                    text(
                        "SELECT record_kind,phase,resume_start,body_ciphertext IS NOT NULL AS has_body FROM agent_memory_context_refresh WHERE tenant_id=:tenant AND execution_id=:execution"
                    ),
                    {
                        "tenant": scope.conversation.tenant_id.encode(),
                        "execution": scope.execution_id.encode(),
                    },
                )
            )
            .mappings()
            .all()
        )
    assert (
        sum(
            row["record_kind"] == "RESULT"
            and row["phase"] == "CAPTURED"
            and row["has_body"]
            for row in rows
        )
        == 1
    )
    if reserve_then_expire:
        assert all(
            row["resume_start"] is None for row in rows if row["record_kind"] == "WAIT"
        )
    else:
        assert any(
            row["record_kind"] == "WAIT" and row["resume_start"] == "DONE"
            for row in rows
        )
