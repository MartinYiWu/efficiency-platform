"""授权刷新实际发送边界；仅使用离线Provider与MockTransport。"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from efficiency_platform_agent.context.dispatch import ControlledModelProvider
from efficiency_platform_agent.core.paid_budget import PaidBudgetPlan, PaidPriceLimit
from efficiency_platform_agent.core.run_context_binding import bind_run_context
from efficiency_platform_agent.orchestration.context_gate import FencedModelProvider
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.providers.llm.deepseek import (
    _json_value,
    _serialize_message,
)
from efficiency_platform_agent.providers.paid_http import PaidHttpTransport
from tests.unit.context.test_entrypoint_coverage import Provider, configured, request
from tests.unit.memory.test_provider_fence_capabilities import binding


class SendGate:
    def __init__(self):
        self.held = False
        self.events = []

    def acquire(self):
        return self.send_lease_execution()

    @asynccontextmanager
    async def guard_execution(self, *args):
        raise AssertionError("准备阶段不得取得旧长锁")
        yield

    @asynccontextmanager
    async def send_lease_execution(self, *args):
        assert not self.held
        self.held = True
        self.events.append("lease")
        try:
            yield None
        finally:
            self.events.append("release")
            self.held = False


@pytest.mark.parametrize("paid", [False, True])
async def test_wait_cpu_capability_never_reserves_or_sends(tmp_path, paid):
    from efficiency_platform_agent.core.memory_execution import (
        MemoryWaitCheckpointCapability,
        bind_memory_wait_checkpoint_capability,
    )
    from tests.unit.memory.test_send_lease_authority import case

    scope = case()[1]
    cap = MemoryWaitCheckpointCapability(
        scope, "runtime", "wait", "op", 1, None, 1, 1, "c" * 64, 200, "cap"
    )
    with bind_memory_wait_checkpoint_capability(cap):
        if paid:
            book = SqlitePaidBudgetLedger(tmp_path / "no-authorization.sqlite3")
            async with httpx.AsyncClient(
                transport=PaidHttpTransport(
                    book,
                    httpx.MockTransport(lambda r: pytest.fail("不得发送")),
                    "deepseek",
                )
            ) as client:
                from efficiency_platform_agent.providers.paid_http import (
                    PaidBudgetTransportError,
                )

                with pytest.raises(PaidBudgetTransportError) as error:
                    await client.post(
                        "https://offline.invalid/chat/completions",
                        json={"model": "fake", "max_tokens": 10},
                    )
                assert error.value.code == "MEMORY_CPU_CHECKPOINT_SEND_FORBIDDEN"
        else:
            dispatch, _, _, _ = configured()
            inner = Provider()
            provider = ControlledModelProvider(
                inner, dispatch, "deepseek", "fake", paid_transport=False
            )
            with pytest.raises(
                PermissionError, match="MEMORY_CPU_CHECKPOINT_SEND_FORBIDDEN"
            ):
                await provider.complete(request())
            assert not inner.requests


async def test_sent_unknown_blocks_provider_retry_before_second_paid_reservation(
    tmp_path,
):
    from efficiency_platform_agent.core.execution_control import (
        RunControl,
        execution_scope,
    )
    from efficiency_platform_agent.providers.deepseek_stream import (
        DeepSeekStreamingProvider,
    )

    dispatch, _, store, _ = configured()

    class Refresh:
        async def validate_manifest_authorization(self, *args):
            return False

    dispatch.install_refresh(Refresh(), object())
    book = SqlitePaidBudgetLedger(tmp_path / "unknown-budget.sqlite3")
    book.authorize(
        PaidBudgetPlan(
            "offline",
            3,
            100,
            int(time.time() * 1000) + 10000,
            3,
            100,
            10000,
            1,
            2,
            *([1000000] * 6),
        ),
        (
            PaidPriceLimit(
                "deepseek",
                "fake",
                10000,
                100,
                10,
                "synthetic",
                "test-v1",
                20000,
                1,
                0,
                1,
            ),
        ),
    )
    sends = []
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(lambda r: (sends.append(r), httpx.Response(429))[1]),
            "deepseek",
        )
    ) as client:
        raw = DeepSeekStreamingProvider(
            client,
            "fake",
            api_key="synthetic",
            base_url="https://offline.invalid",
            max_retries=1,
        )
        provider = ControlledModelProvider(
            raw, dispatch, "deepseek", "fake", paid_transport=True
        )
        control = RunControl()
        with execution_scope(control):
            try:
                result = await provider.complete(request())
                assert result.error is not None
            except (PermissionError, ValueError):
                pass
    assert next(iter(store.receipts.values())).status == "UNKNOWN"
    assert len(sends) == control.calls == book.snapshot()["calls"] == 1
    assert book.snapshot()["inflight"] == 0


async def test_prepare_has_no_pg_lease_and_nonpaid_final_edge_is_fenced():
    gate = SendGate()
    dispatch, _, _, _ = configured()
    original = dispatch.controller.prepare

    async def prepare(*args, **kwargs):
        assert not gate.held
        gate.events.append("prepare")
        return await original(*args, **kwargs)

    dispatch.controller.prepare = prepare

    class Inner(Provider):
        async def complete(self, value):
            assert gate.held
            gate.events.append("send")
            return await super().complete(value)

    provider = FencedModelProvider(
        ControlledModelProvider(
            Inner(), dispatch, "deepseek", "fake", paid_transport=False
        ),
        gate,
        "official",
        send_authority=gate,
    )
    with bind_run_context(binding()):
        await provider.complete(request())
    assert gate.events == ["prepare", "lease", "send", "release"]


@pytest.mark.parametrize("early_close", [False, True])
async def test_paid_lease_starts_after_reserve_and_releases_after_bottom_close(
    tmp_path, early_close
):
    gate = SendGate()
    book = SqlitePaidBudgetLedger(tmp_path / "synthetic-budget.sqlite3")
    book.authorize(
        PaidBudgetPlan(
            "offline",
            3,
            100,
            int(time.time() * 1000) + 10000,
            3,
            100,
            10000,
            2,
            2,
            *([1000000] * 6),
        ),
        (
            PaidPriceLimit(
                "deepseek",
                "fake",
                10000,
                100,
                10,
                "synthetic",
                "test-v1",
                20000,
                1,
                0,
                1,
            ),
        ),
    )
    original_reserve = book.reserve

    def reserve(*args, **kwargs):
        assert not gate.held
        gate.events.append("reserve")
        return original_reserve(*args, **kwargs)

    book.reserve = reserve

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            assert gate.held
            yield b"synthetic"

        async def aclose(self):
            assert gate.held
            gate.events.append("bottom-close")

    def upstream(value):
        assert gate.held
        gate.events.append("send")
        return httpx.Response(200, stream=Body())

    dispatch, _, _, _ = configured()
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(book, httpx.MockTransport(upstream), "deepseek")
    ) as client:

        class HttpProvider(Provider):
            async def complete(self, value):
                payload = {
                    "model": "fake",
                    "messages": [
                        _serialize_message(m, supports_developer_role=True)
                        for m in value.messages
                    ],
                    **_json_value(value.options),
                }
                async with client.stream(
                    "POST", "https://offline.invalid/chat/completions", json=payload
                ) as response:
                    if not early_close:
                        await response.aread()
                assert not gate.held
                return await super().complete(value)

        inner = HttpProvider()
        provider = FencedModelProvider(
            ControlledModelProvider(
                inner, dispatch, "deepseek", "fake", paid_transport=True
            ),
            gate,
            "official",
            send_authority=gate,
        )
        with bind_run_context(binding()):
            await provider.complete(request())
    assert gate.events == ["reserve", "lease", "send", "bottom-close", "release"]


@pytest.mark.parametrize("capture_fails", [False, True])
async def test_complete_response_is_captured_before_return_without_second_dispatch(
    capture_fails,
):
    class Authority(SendGate):
        permit = object()
        complete = False

        async def issue(self, prepared, operation):
            assert self.held
            return self.permit

        def response_received(self, permit, *, complete):
            assert permit is self.permit
            self.complete = complete

        @asynccontextmanager
        async def result_scope(self, permit):
            assert permit is self.permit and self.complete and not self.held
            self.events.append("result-lease")
            yield

    authority = Authority()
    dispatch, _, store, _ = configured()
    inner = Provider()
    captured = []

    async def capture(manifest, operation, permit, result):
        assert permit is authority.permit
        captured.append(result)
        if capture_fails:
            raise ValueError("MEMORY_RESULT_UNAVAILABLE")
        await store.record_receipt(manifest, "SUCCEEDED")
        return "authenticated-result"

    store.capture_result_once = capture
    provider = FencedModelProvider(
        ControlledModelProvider(
            inner, dispatch, "deepseek", "fake", paid_transport=False
        ),
        authority,
        "official",
        send_authority=authority,
    )
    with bind_run_context(binding()):
        if capture_fails:
            with pytest.raises(ValueError, match="MEMORY_RESULT_UNAVAILABLE"):
                await provider.complete(request())
        else:
            result = await provider.complete(request())
            assert captured == [result]
        with pytest.raises(ValueError, match="CONTEXT_OPERATION_BLOCKED"):
            await provider.complete(request())
    assert len(inner.requests) == len(captured) == 1
    assert next(iter(store.receipts.values())).status == (
        "UNKNOWN" if capture_fails else "SUCCEEDED"
    )


@pytest.mark.parametrize(
    "event",
    [
        "refresh",
        "stop",
        "deadline",
        "source",
        "cancel",
        "budget",
        "false_receipt",
        "third_ack",
        "aligned_successor",
    ],
)
async def test_late_ttl_waits_in_original_transport_without_second_reservation(
    tmp_path,
    event,
):
    from efficiency_platform_agent.core.execution_control import (
        RunControl,
        execution_scope,
    )
    from efficiency_platform_agent.core.memory_execution import MemoryExecutionRecord
    from efficiency_platform_agent.core.memory_refresh import WaitPhase
    from efficiency_platform_agent.core.run_context_binding import RunContextBinding
    from efficiency_platform_agent.memory.execution_authority import (
        MemorySendLeaseAuthority,
    )
    from efficiency_platform_agent.security.memory_packet import (
        memory_packet_digest,
        memory_packet_semantic_digest,
    )
    from tests.unit.memory.test_send_lease_authority import case

    dispatch, _, store, scope = configured()
    old_context = case()[0].memory_context
    old_packet = replace(
        old_context.packet,
        scope=scope.conversation,
        task_id=scope.task_id,
        execution_id=scope.execution_id,
    )
    old_context = replace(
        old_context,
        packet=old_packet,
        packet_digest=memory_packet_digest(old_packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(old_packet),
    )
    binding_value = RunContextBinding(
        scope.conversation, scope.task_id, scope.execution_id, 200, old_context
    )
    now = [150]
    dispatch.controller._clock = lambda: now[0]

    class Validator:
        async def validate(self, *args):
            pass

    dispatch.controller.install_memory_validator(Validator())
    resolve = dispatch.authority.resolve

    async def memory_plan(*args):
        plan = await resolve(*args)
        return replace(
            plan,
            packet=old_packet,
            operation=replace(
                plan.operation, deadline_epoch_seconds=200, memory_disabled=False
            ),
        )

    dispatch.authority.resolve = memory_plan
    record = MemoryExecutionRecord(
        old_context,
        "runtime",
        "OPERATIONS",
        "a" * 64,
        200,
        "ACTIVE",
        1,
        old_packet.grant_epoch,
        old_packet.source_epoch,
        old_packet.deletion_epoch,
    )

    class MemoryStore:
        async def get(self, *args):
            return record

    waiting = asyncio.Event()
    successor_notified = asyncio.Event()
    graph_ready = []
    source_current = [True]
    notified = []

    class Refresh:
        async def begin_wait_intent(
            self, scope_value, runtime, operation, attempt, phase, **kwargs
        ):
            assert not gate.held and phase == WaitPhase.RESERVED
            assert (
                kwargs["canonical_request_hmac"]
                == next(iter(store.manifests.values())).canonical_request_hmac
            )
            waiting.set()
            return "wait"

        async def finish_wait(self, *args):
            assert graph_ready == (
                ["original-graph-frame"] if event == "refresh" else []
            )

        async def get_wait(self, *args, **kwargs):
            if not source_current[0]:
                raise PermissionError("SOURCE_REVOKED")
            manifest = next(iter(store.manifests.values()))
            return SimpleNamespace(
                refresh_count=3
                if event == "third_ack" and record.context.packet.packet_revision == 2
                else 0,
                wait_event_id=kwargs.get("wait_event_id", "wait-2"),
                scope=scope.conversation,
                task_id=scope.task_id,
                execution_id=scope.execution_id,
                runtime_id="runtime",
                expected_packet_revision=2,
                expected_execution_revision=1,
                expected_current_context_fingerprint=__import__("hashlib")
                .sha256(
                    json.dumps(
                        record.context.metadata(),
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode()
                )
                .hexdigest(),
                logical_operation_id=manifest.operation_id,
                canonical_request_hmac=manifest.canonical_request_hmac,
                attempt=1,
                stage_id=None,
                stage_slot=None,
                wait_phase=WaitPhase.RESERVED,
                original_deadline=200,
            )

        async def validate_manifest_authorization(self, *args):
            return True

        async def get_wait_receipt(self, *args):
            if record.context.packet.packet_revision == 1:
                return None
            import hashlib

            fingerprint = hashlib.sha256(
                json.dumps(
                    record.context.metadata(),
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            return SimpleNamespace(
                code="CONTEXT_REFRESHED",
                candidate_phase="ACKED",
                state="ACTIVE",
                dispatch_allowed=event != "false_receipt",
                wait_event_id="wait-2" if event == "aligned_successor" else "wait",
                packet_revision=record.context.packet.packet_revision,
                execution_revision=1,
                current_packet_revision=record.context.packet.packet_revision,
                current_context_fingerprint=fingerprint,
            )

        async def get_wait_outcome(self, conversation, execution_id, wait_id):
            if (
                event == "aligned_successor"
                and wait_id == "wait"
                and record.context.packet.packet_revision == 2
            ):
                import hashlib

                fp = hashlib.sha256(
                    json.dumps(
                        record.context.metadata(),
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                return SimpleNamespace(
                    code="MEMORY_REFRESH_PACKET_EXPIRED",
                    candidate_phase="APPLIED_EXPIRED",
                    state="WAITING_CONTEXT",
                    dispatch_allowed=False,
                    wait_event_id="wait",
                    packet_revision=2,
                    current_packet_revision=2,
                    execution_revision=1,
                    current_context_fingerprint=fp,
                    next_wait_event_id="wait-2",
                    refresh_count=1,
                )
            return await self.get_wait_receipt(conversation, execution_id, wait_id)

    async def on_wait(wait_id, execution_id, runtime_id):
        notified.append((wait_id, execution_id, runtime_id))
        if wait_id == "wait-2":
            successor_notified.set()

    dispatch.install_refresh(Refresh(), MemoryStore(), on_wait=on_wait)
    if event == "refresh":

        async def ready_graph_wait(send, wait_id):
            assert send._reservation is not None and not send.sent and wait_id == "wait"
            graph_ready.append("original-graph-frame")
            return False

        dispatch.install_wait_checkpoint_callback(ready_graph_wait)

    class Gate(SendGate):
        @asynccontextmanager
        async def send_lease_execution(self, *args):
            if now[0] >= record.context.packet.expires_at:
                raise PermissionError("MEMORY_PACKET_EXPIRED")
            async with super().send_lease_execution():
                yield

        @asynccontextmanager
        async def result_lease_execution(self, *args):
            yield

    gate = Gate()
    send_authority = MemorySendLeaseAuthority(gate, MemoryStore(), "official")

    async def capture(manifest, operation, permit, result):
        assert await send_authority.validate(permit)
        await store.record_receipt(manifest, "SUCCEEDED")
        return "result"

    store.capture_result_once = capture
    book = SqlitePaidBudgetLedger(tmp_path / "budget.sqlite3")
    book.authorize(
        PaidBudgetPlan(
            "offline",
            3,
            100,
            int(time.time() * 1000) + 10000,
            3,
            100,
            10000,
            2,
            2,
            *([1000000] * 6),
        ),
        (
            PaidPriceLimit(
                "deepseek",
                "fake",
                10000,
                100,
                10,
                "synthetic",
                "test-v1",
                20000,
                1,
                0,
                1,
            ),
        ),
    )
    reservations = []
    original_reserve = book.reserve

    def reserve(*args, **kwargs):
        value = original_reserve(*args, **kwargs)
        reservations.append(value)
        now[0] = 161
        return value

    book.reserve = reserve
    sends = []

    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            book,
            httpx.MockTransport(
                lambda r: (sends.append(r), httpx.Response(200, text="ok"))[1]
            ),
            "deepseek",
        )
    ) as client:

        class HttpProvider(Provider):
            async def complete(self, value):
                await client.post(
                    "https://offline.invalid/chat/completions",
                    json={
                        "model": "fake",
                        "messages": [
                            _serialize_message(m, supports_developer_role=True)
                            for m in value.messages
                        ],
                        **_json_value(value.options),
                    },
                )
                return await super().complete(value)

        provider = FencedModelProvider(
            ControlledModelProvider(
                HttpProvider(), dispatch, "deepseek", "fake", paid_transport=True
            ),
            gate,
            "official",
            send_authority=send_authority,
        )
        control = RunControl()
        with bind_run_context(binding_value), execution_scope(control):
            task = asyncio.create_task(provider.complete(request()))
            await asyncio.wait_for(waiting.wait(), 2)
            assert len(reservations) == control.calls == 1 and not sends
            assert notified == [("wait", scope.execution_id, "runtime")]
            if event in {"refresh", "false_receipt", "third_ack", "aligned_successor"}:
                packet = replace(
                    old_packet, packet_revision=2, issued_at=161, expires_at=190
                )
                record = replace(
                    record,
                    context=replace(
                        old_context,
                        packet=packet,
                        packet_digest=memory_packet_digest(packet),
                    ),
                )
                if event == "aligned_successor":
                    await asyncio.wait_for(successor_notified.wait(), 1)
                    assert not sends and len(reservations) == control.calls == 1
                    packet = replace(
                        packet, packet_revision=3, issued_at=161, expires_at=190
                    )
                    record = replace(
                        record,
                        context=replace(
                            record.context,
                            packet=packet,
                            packet_digest=memory_packet_digest(packet),
                        ),
                    )
                if event == "false_receipt":
                    with pytest.raises(
                        PermissionError, match="CONTINUATION_AUTH_UNSUPPORTED"
                    ):
                        await asyncio.wait_for(task, 2)
                else:
                    await asyncio.wait_for(task, 2)
            else:
                if event == "stop":
                    control.stop()
                elif event == "deadline":
                    now[0] = 200
                elif event == "source":
                    source_current[0] = False
                elif event == "budget":
                    book.stop("offline", "synthetic")
                else:
                    task.cancel()
                with pytest.raises(
                    asyncio.CancelledError if event == "cancel" else Exception
                ):
                    await asyncio.wait_for(task, 2)
    assert len(sends) == (
        1 if event in {"refresh", "third_ack", "aligned_successor"} else 0
    )
    assert len(reservations) == control.calls == 1
    assert not gate.held and not control.http_tasks
