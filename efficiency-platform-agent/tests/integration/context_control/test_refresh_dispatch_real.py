"""RF04真实双库/内部HTTP/生产Provider链；只有外部模型使用MockTransport。"""

import asyncio
import json
import os
import time
from dataclasses import asdict, replace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from efficiency_platform_agent.api.memory_routes import build_memory_router
from efficiency_platform_agent.context.controller import ContextController
from efficiency_platform_agent.context.dispatch import (
    ContextDispatch,
    ControlledModelProvider,
)
from efficiency_platform_agent.contracts.context_control import ContextManifestModel
from efficiency_platform_agent.core.context_control import ModelCapacity, WindowLimits
from efficiency_platform_agent.core.context_dispatch import model_stage
from efficiency_platform_agent.core.context_ports import ContextMetadata
from efficiency_platform_agent.core.diagnostics import safe_exception_location
from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.core.memory import ExecutionScope
from efficiency_platform_agent.core.memory_execution import MemoryExecutionGrant
from efficiency_platform_agent.core.memory_refresh import (
    MemoryContextResume,
    ResumeMode,
)
from efficiency_platform_agent.core.paid_budget import PaidBudgetPlan, PaidPriceLimit
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    bind_run_context,
)
from efficiency_platform_agent.harness.context_authority import ServerDispatchAuthority
from efficiency_platform_agent.harness.hr_factory import internal_hr_authorizer
from efficiency_platform_agent.memory.context_refresh import MemoryContextRefreshService
from efficiency_platform_agent.memory.execution_authority import (
    MemorySendLeaseAuthority,
    StoredMemoryPacketValidator,
)
from efficiency_platform_agent.orchestration.context_gate import FencedModelProvider
from efficiency_platform_agent.persistence.context_manifest import (
    MySqlContextManifestStore,
)
from efficiency_platform_agent.persistence.memory_context_refresh import (
    MySqlMemoryContextRefreshStore,
)
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.providers.deepseek_stream import (
    DeepSeekStreamingProvider,
)
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)
from efficiency_platform_agent.providers.paid_http import PaidHttpTransport
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)
from tests.integration.context_control.test_memory_stop_http import running
from tests.integration.memory.test_refresh_persistence import (
    refresh_case as refresh_case,  # noqa: PLC0414
)

pytestmark = pytest.mark.skipif(
    os.environ.get("MEMORY_IT_ENABLED") != "1", reason="需root显式本机隔离双库"
)


@pytest.mark.parametrize("refresh_case", ["http-tenant"], indirect=True)
@pytest.mark.parametrize("expired_candidates", [0, 2])
async def test_real_reserved_ttl_http_refresh_keeps_one_original_paid_dispatch(
    refresh_case, tmp_path, expired_candidates
):
    await _reserved_case(refresh_case, tmp_path, expired_candidates)


@pytest.mark.parametrize("refresh_case", ["http-tenant"], indirect=True)
async def test_real_third_pending_candidate_preserves_original_paid_frame(
    refresh_case, tmp_path
):
    await _reserved_case(refresh_case, tmp_path, 2, concurrent_third=True)


async def _reserved_case(
    refresh_case, tmp_path, expired_candidates, *, concurrent_third=False
):
    _original_scope, original_record, store, registry, _ = refresh_case
    registry.clock = time.time
    now = int(time.time())
    node, model = "customer-service:answer_general", "rf04-offline-model"
    packet = replace(
        original_record.context.packet,
        task_id=uuid4().hex,
        execution_id=uuid4().hex,
        issued_at=now,
        expires_at=now + 2,
    )
    context = replace(
        original_record.context,
        packet=packet,
        deadline_epoch_seconds=now + 60,
        execution_grants=(
            MemoryExecutionGrant(node, "customer-service", "assistant_response"),
        ),
        packet_digest=memory_packet_digest(packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(packet),
    )
    scope = ExecutionScope(
        packet.scope,
        packet.task_id,
        packet.execution_id,
        node,
        "assistant_response",
        "customer-service",
    )
    runtime_id = uuid4().hex
    record, _ = await store.claim(
        context, runtime_id, "CUSTOMER_SERVICE", "c" * 64, now + 60
    )
    await registry.enroll_no_checkpoint(scope, runtime_id)
    send_authority = MemorySendLeaseAuthority(registry, store)
    registry.install_result_authority(send_authority)
    manifests = MySqlContextManifestStore(store.engine, memory_execution_store=store)
    manifests.install_result_authority(send_authority)
    options = JsonObject((("max_tokens", 50),))
    capacity = ModelCapacity(
        "deepseek",
        model,
        "rf04/1",
        32000,
        20000,
        50,
        "conservative-utf8/1",
        "openai-chat/1",
        "NO_REASONING",
        True,
        "synthetic-only",
    )
    metadata = ContextMetadata(
        node,
        "rf04-window/1",
        "rf04-prompt/1",
        "none/1",
        "none/1",
        1,
        capacity,
        WindowLimits(32000, 20000, 50, 100, 19800),
        options,
    )
    controller = ContextController(
        ConservativeRequestTokenCounter(),
        manifests,
        b"rf04-offline-hmac-key-32-bytes----",
        validator=StoredMemoryPacketValidator(store),
    )
    dispatch = ContextDispatch(
        controller,
        manifests,
        ServerDispatchAuthority(
            {("deepseek", model, node): metadata},
            {node: ("customer-service", "assistant_response")},
            memory_execution_store=store,
        ),
    )
    service = MemoryContextRefreshService(
        registry,
        MySqlMemoryContextRefreshStore(store),
        frame_verifier=dispatch.verify_wait_frame,
        binding_updater=dispatch.update_wait_frame_binding,
    )
    app = FastAPI()

    @app.exception_handler(Exception)
    async def safe_failure(_request, error):
        facts = {
            "code": "MEMORY_AUTHORITY_UNAVAILABLE",
            "error_type": type(error).__name__,
            "location": safe_exception_location(error),
        }
        print("RF04_SAFE_FAILURE " + json.dumps(facts), flush=True)
        return JSONResponse(status_code=503, content=facts)

    secret = "rf04-synthetic-internal-http-secret"
    app.include_router(
        build_memory_router(
            store, internal_hr_authorizer(secret), None, refresh_service=service
        )
    )
    headers = {
        "Authorization": "Bearer " + secret,
        "X-Tenant-ID": scope.conversation.tenant_id,
    }
    prefix = f"/internal/v1/memory/executions/{scope.execution_id}"
    book = SqlitePaidBudgetLedger(tmp_path / "rf04-mocktransport-budget.sqlite3")
    book.authorize(
        PaidBudgetPlan(
            "rf04-offline",
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
                50,
                10,
                "synthetic-only MockTransport",
                "rf04/1",
                200000,
                1,
                0,
                1,
            ),
        ),
    )
    reserve = book.reserve
    reservations = []

    def expire_after_original_reservation(*args, **kwargs):
        reservation = reserve(*args, **kwargs)
        reservations.append(reservation)
        time.sleep(2.1)
        return reservation

    book.reserve = expire_after_original_reservation
    sends, receipts = [], []
    data = [
        {
            "choices": [
                {"delta": {"content": "original-response"}, "finish_reason": None}
            ]
        },
        {
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "prompt_cache_hit_tokens": 0,
            },
        },
    ]
    sse = (
        "".join("data: " + json.dumps(item) + "\n\n" for item in data)
        + "data: [DONE]\n\n"
    )

    def upstream(request):
        sends.append(request)
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse.encode()
        )

    async with running(app) as internal:
        faults = [0]
        third_a, third_poll, third_release = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )
        background = []
        paid_task = None
        get_wait = service.get_wait

        async def observed_wait(*args, **kwargs):
            value = await get_wait(*args, **kwargs)
            if (
                third_a.is_set()
                and asyncio.current_task() is paid_task
                and value is not None
                and value.refresh_count == 3
            ):
                third_poll.set()
            return value

        service.get_wait = observed_wait

        async def expire_installed_candidate(point):
            if (
                point == "after_a"
                and concurrent_third
                and faults[0] == expired_candidates
            ):
                third_a.set()
                await asyncio.wait_for(third_release.wait(), 3)
            if point == "after_b" and faults[0] < expired_candidates:
                faults[0] += 1
                await asyncio.sleep(2.1)

        service.fault_hook = expire_installed_candidate

        async def on_wait(wait_id, execution_id, emitted_runtime):
            assert emitted_runtime == runtime_id and execution_id == scope.execution_id
            response = await internal.get(prefix + "/wait", headers=headers)
            assert response.status_code == 200
            wait = await service.get_wait(scope.conversation, scope.execution_id)
            assert wait.wait_event_id == wait_id and wait.wait_phase.value == "RESERVED"
            current = await store.get(scope.conversation.tenant_id, scope.execution_id)
            assert not sends and len(reservations) == 1
            async with store.engine.connect() as connection:
                raw_manifest = (
                    await connection.execute(
                        text(
                            "SELECT metadata_json FROM agent_context_manifest WHERE tenant_id=:tenant AND task_id=:task AND execution_id=:execution AND operation_id=:operation AND attempt=:attempt"
                        ),
                        {
                            "tenant": scope.conversation.tenant_id.encode(),
                            "task": scope.task_id.encode(),
                            "execution": scope.execution_id.encode(),
                            "operation": wait.logical_operation_id.encode(),
                            "attempt": wait.attempt,
                        },
                    )
                ).scalar_one()
            manifest = ContextManifestModel.model_validate_json(raw_manifest).to_core()
            original_receipt = await manifests.get_operation_receipt(
                scope, wait.logical_operation_id
            )
            assert original_receipt.status == "NOT_SENT"
            assert (
                wait.canonical_request_hmac == manifest.canonical_request_hmac
                and manifest.packet_revision == 1
            )
            packet = replace(
                current.context.packet,
                packet_revision=wait.expected_packet_revision + 1,
                issued_at=int(time.time()),
                expires_at=int(time.time()) + 2,
            )
            refreshed = replace(
                current.context,
                packet=packet,
                packet_digest=memory_packet_digest(packet),
            )
            command = MemoryContextResume(
                wait_id,
                wait.expected_packet_revision,
                wait.expected_execution_revision,
                uuid4().hex,
                record.request_fingerprint,
                ResumeMode.REFRESH,
                False,
                "memory-context-resume/2",
                wait.logical_operation_id,
                wait.canonical_request_hmac,
                wait.attempt,
                wait.expected_current_context_fingerprint,
                refreshed,
            )
            body = asdict(command)
            body["refreshed_context"] = {
                "schema_version": "memory-context/1",
                "memory_mode": "EXACT_ONLY",
                "scope": asdict(scope.conversation),
                "packet": asdict(packet),
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

            async def post():
                return await internal.post(
                    prefix + "/resume", headers=headers, json=body
                )

            if concurrent_third and len(receipts) == expired_candidates:
                resume_task = asyncio.create_task(post())

                async def observe_pending():
                    try:
                        await asyncio.wait_for(third_a.wait(), 2)
                        await asyncio.wait_for(third_poll.wait(), 2)
                        await asyncio.sleep(0.1)
                        assert paid_task is not None and not paid_task.done(), (
                            "THIRD_PENDING_ORIGINAL_FRAME_LOST"
                        )
                        assert (
                            dispatch._waiting_frames
                            and not sends
                            and len(reservations)
                            == control.calls
                            == book.snapshot()["calls"]
                            == 1
                        )
                        print("RF04RACE_THIRD_PENDING_FRAME_LIVE", flush=True)
                    finally:
                        third_release.set()
                    response = await resume_task
                    assert response.status_code == 200
                    facts = response.json()
                    assert (
                        facts["candidate_phase"] == "ACKED"
                        and facts["refresh_count"] == 3
                        and facts["dispatch_allowed"] is True
                    )
                    receipts.append(facts)

                background.extend((resume_task, asyncio.create_task(observe_pending())))
                return
            resumed = await post()
            facts = (
                resumed.json()
                if resumed.headers.get("content-type", "").startswith(
                    "application/json"
                )
                else {}
            )
            assert resumed.status_code == (
                409 if len(receipts) < expired_candidates else 200
            ), {
                "status": resumed.status_code,
                "code": facts.get("code"),
                "error_type": facts.get("error_type"),
                "location": facts.get("location"),
            }
            receipts.append(resumed.json())
            if len(receipts) <= expired_candidates:
                assert receipts[-1]["candidate_phase"] == "APPLIED_EXPIRED"
                assert (
                    receipts[-1]["dispatch_allowed"] is False
                    and receipts[-1]["next_wait_event_id"]
                )
            else:
                assert (
                    receipts[-1]["dispatch_allowed"] is True
                    and receipts[-1]["refresh_count"] == expired_candidates + 1
                )

        dispatch.install_refresh(service, store, on_wait=on_wait)
        async with httpx.AsyncClient(
            transport=PaidHttpTransport(
                book,
                httpx.MockTransport(upstream),
                "deepseek",
                require_context_guard=True,
            )
        ) as client:
            raw = DeepSeekStreamingProvider(
                client,
                model,
                api_key="synthetic-only",
                base_url="https://offline.invalid",
                max_retries=0,
            )
            provider = FencedModelProvider(
                ControlledModelProvider(
                    raw, dispatch, "deepseek", model, paid_transport=True
                ),
                registry,
                "NO_CHECKPOINT",
                send_authority=send_authority,
            )
            binding = RunContextBinding(
                scope.conversation,
                scope.task_id,
                scope.execution_id,
                record.deadline_epoch_seconds,
                context,
            )
            control = RunControl(timeout_ms=60000)
            with (
                bind_run_context(binding),
                execution_scope(control),
                model_stage(
                    "rf04-original-operation", b"original-frozen-input", node_id=node
                ),
            ):
                paid_task = asyncio.create_task(
                    provider.complete(
                        ProviderRequest(
                            "rf04/1",
                            (ProviderMessage("user", "synthetic input"),),
                            options,
                            15000,
                        )
                    )
                )
                try:
                    result = await asyncio.wait_for(paid_task, 15)
                    if background:
                        await asyncio.gather(*background)
                finally:
                    third_release.set()
                    if background:
                        await asyncio.gather(*background, return_exceptions=True)
    assert result.error is None and result.message.content == "original-response"
    assert (
        len(reservations)
        == len(sends)
        == control.calls
        == book.snapshot()["calls"]
        == 1
    )
    assert len(receipts) == expired_candidates + 1
    assert book.snapshot()["inflight"] == 0
    current = await store.get(scope.conversation.tenant_id, scope.execution_id)
    assert (
        current.deadline_epoch_seconds == record.deadline_epoch_seconds
        and current.context.packet.packet_revision == expired_candidates + 2
    )
    receipt = await manifests.get_operation_receipt(scope, "rf04-original-operation")
    assert receipt.status == "SUCCEEDED"
    async with store.engine.connect() as connection:
        captured = (
            (
                await connection.execute(
                    text(
                        "SELECT phase,body_ciphertext IS NOT NULL AS has_body FROM agent_memory_context_refresh WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='RESULT'"
                    ),
                    {
                        "tenant": scope.conversation.tenant_id.encode(),
                        "execution": scope.execution_id.encode(),
                    },
                )
            )
            .mappings()
            .one()
        )
    assert captured["phase"] == "CAPTURED" and captured["has_body"] == 1
