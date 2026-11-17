"""真实受控 Provider + PaidHttp + MockTransport 的离线链路验证。"""

import json
import sqlite3
import time
from dataclasses import replace
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from efficiency_platform_agent.capabilities.model.memory_derive import (
    DeriveDispatchAuthority,
    DeriveGateway,
)
from efficiency_platform_agent.context.controller import ContextController
from efficiency_platform_agent.context.dispatch import (
    ContextDispatch,
    ControlledModelProvider,
)
from efficiency_platform_agent.core.context_control import ModelCapacity, WindowLimits
from efficiency_platform_agent.core.context_dispatch import current_model_stage
from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.core.paid_budget import (
    PaidBudgetPlan,
    PaidPriceLimit,
    paid_scope,
)
from efficiency_platform_agent.memory.derive import (
    DeriveCandidate,
    HydratedDeriveSources,
)
from efficiency_platform_agent.persistence.context_manifest import (
    MySqlContextManifestStore,
)
from efficiency_platform_agent.persistence.context_stage import MySqlContextStageStore
from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher
from efficiency_platform_agent.providers.deepseek_stream import (
    DeepSeekStreamingProvider,
)
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)
from efficiency_platform_agent.providers.paid_http import PaidHttpTransport
from tests.unit.memory.test_derive_budget import setup_store
from tests.unit.memory.test_summary_contracts import segment, source
from tests.unit.persistence.test_context_manifest import LocalEngine


@pytest.fixture
async def harness(tmp_path):
    ledger, store, operation = setup_store(tmp_path)
    deadline = operation.deadline_epoch_seconds
    ledger.authorize(
        PaidBudgetPlan(
            "budget",
            20,
            100000,
            deadline * 1000,
            20,
            100000,
            60000,
            1,
            2,
            1000000,
            1000000,
            1000000,
            1000000,
            1000000,
            1000000,
        ),
        (
            PaidPriceLimit(
                "deepseek",
                "fixture-model",
                100000,
                500,
                10,
                "synthetic fixture only",
                "fixture",
                100000,
                1,
                0,
                1,
            ),
        ),
    )
    # 真实 manifest/stage SQL 适配器仅绑定临时 SQLite。
    engine = LocalEngine(tmp_path / "context.sqlite")
    with engine.engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE agent_context_stage (tenant_id BLOB,task_id BLOB,execution_id BLOB,stage_id BLOB,scope_hash TEXT,semantic_hash TEXT,deadline INTEGER,current_slot INTEGER,status TEXT,operation_id_1 TEXT,operation_id_2 TEXT,operation_id_3 TEXT,PRIMARY KEY(tenant_id,task_id,execution_id,stage_id))"
            )
        )
    manifests = MySqlContextManifestStore(cast(AsyncEngine, engine))
    stages = MySqlContextStageStore(cast(AsyncEngine, engine), b"k" * 32)
    sources = (
        source(
            scope=source().scope.model_copy(
                update={"tenant_id": "t", "user_id": "u", "session_id": "s"}
            ),
            expires_at=deadline,
        ),
    )
    summary = segment(scope=sources[0].scope, expires_at=deadline)
    answer = DeriveCandidate(
        mode="SUMMARY", summary=summary, proposals=()
    ).model_dump_json()
    state = {
        "sent": [],
        "responses": [answer],
        "status": 200,
        "checks": 0,
        "body": "fixture original source",
    }

    async def upstream(request):
        state["sent"].append(request)
        if state["status"] != 200:
            return httpx.Response(state["status"])
        content = (
            state["responses"].pop(0)
            if len(state["responses"]) > 1
            else state["responses"][0]
        )
        data = {
            "choices": [
                {"delta": {"content": content}, "finish_reason": "stop", "index": 0}
            ]
        }
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content="data: " + json.dumps(data) + "\n\ndata: [DONE]\n\n",
        )

    class Authority:
        async def check(self, scope, mode, selected, op):
            assert selected == sources and scope == sources[0].scope and op == operation
            state["checks"] += 1

    class Hydrator:
        async def hydrate(self, scope, mode, selected, op):
            return HydratedDeriveSources((state["body"],), (), 1)

    class Validator:
        async def validate(self, scope, packet, deps, op):
            assert scope == operation.scope and len(deps) == 1
            ledger.check_execution("t", "run")

    class RecordingCounter(ConservativeRequestTokenCounter):
        def __init__(self):
            self.full_calls = 0
            self.fragment_calls = 0

        def measure(self, request, capacity):
            self.full_calls += 1
            return super().measure(request, capacity)

        def measure_messages(self, messages, capacity):
            self.fragment_calls += 1
            return super().measure_messages(messages, capacity)

    counter = RecordingCounter()
    controller = ContextController(counter, manifests, b"k" * 32, validator=Validator())
    authority = DeriveDispatchAuthority()
    dispatch = ContextDispatch(
        controller, manifests, authority, stage_store=stages, hmac_key=b"k" * 32
    )
    transport = PaidHttpTransport(
        ledger,
        httpx.MockTransport(upstream),
        "deepseek",
        allowed_url="https://fixture.test/chat/completions",
        require_context_guard=True,
    )
    async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
        inner = DeepSeekStreamingProvider(
            client,
            "fixture-model",
            api_key="fixture-only",
            base_url="https://fixture.test",
            max_retries=0,
        )
        provider = ControlledModelProvider(
            inner, dispatch, "deepseek", "fixture-model", paid_transport=True
        )
        capacity = ModelCapacity(
            "deepseek",
            "fixture-model",
            "fixture-1",
            100000,
            99000,
            500,
            "conservative-utf8/1",
            "openai-chat/1",
            "NO_REASONING",
            True,
            "fixture-only",
        )
        kwargs = {
            "provider": provider,
            "dispatch_authority": authority,
            "store": store,
            "counter": counter,
            "capacity": capacity,
            "limits": WindowLimits(100000, 99000, 500, 100, 99000),
            "cipher": MemorySnapshotCipher("fixture", {"fixture": b"c" * 32}),
            "hmac_key": b"k" * 32,
            "authorizer": Authority(),
            "hydrator": Hydrator(),
        }
        yield {
            "state": state,
            "gateway": DeriveGateway(**kwargs),
            "kwargs": kwargs,
            "ledger": ledger,
            "store": store,
            "op": operation,
            "sources": sources,
            "scope": sources[0].scope,
            "engine": engine,
        }
    engine.engine.dispose()


async def invoke(h, mode="SUMMARY", **changes):
    args = {
        "scope": h["scope"],
        "mode": mode,
        "sources": h["sources"],
        "operation": h["op"],
    }
    args.update(changes)
    with execution_scope(RunControl()), paid_scope("original-parent"):
        return await h["gateway"].derive(**args)


async def test_summary_sends_once_and_replays_encrypted_result(harness):
    h = harness
    first = await invoke(h)
    second = await invoke(h)
    assert first == second and first.mode == "SUMMARY"
    assert len(h["state"]["sent"]) == 1
    with sqlite3.connect(h["ledger"].path) as db:
        assert db.execute("SELECT attempts FROM execution_operations").fetchone() == (
            1,
        )
        raw = db.execute("SELECT result FROM derive_operations").fetchone()[0]
        assert b"summary" not in raw and b"fixture original source" not in raw


@pytest.mark.parametrize("mode", ["BOTH", "PROPOSALS"])
async def test_per_source_purpose_denial_sends_zero_without_split(harness, mode):
    h = harness
    sources = (
        h["sources"][0].model_copy(update={"allowed_purposes": frozenset({"SUMMARY"})}),
    )
    with pytest.raises(ValueError, match="PURPOSE_DENIED"):
        await invoke(h, mode, sources=sources)
    assert not h["state"]["sent"]


@pytest.mark.parametrize(
    "failure",
    [
        "no-budget",
        "unknown-price",
        "stopped-budget",
        "stopped-run",
        "deadline",
        "capacity",
        "source-bound",
        "window",
    ],
)
async def test_preflight_and_paid_guard_fail_closed_without_send(harness, failure):
    h = harness
    if failure == "no-budget":
        with sqlite3.connect(h["ledger"].path) as db:
            db.execute("DELETE FROM budgets")
    elif failure == "unknown-price":
        with sqlite3.connect(h["ledger"].path) as db:
            db.execute("DELETE FROM prices")
    elif failure == "stopped-budget":
        h["ledger"].stop("budget", "test stop")
    elif failure == "stopped-run":
        h["ledger"].stop_execution("t", "run", context_scope=h["op"].scope.conversation)
    elif failure == "deadline":
        h["op"] = replace(h["op"], deadline_epoch_seconds=int(time.time()) - 1)
    elif failure == "source-bound":
        h["state"]["body"] = "x" * 2001
    elif failure == "window":
        h["gateway"] = DeriveGateway(
            **(h["kwargs"] | {"limits": WindowLimits(100000, 99000, 500, 100, 100)})
        )
    elif failure == "capacity":
        h["gateway"] = DeriveGateway(
            **(
                h["kwargs"]
                | {"capacity": replace(h["kwargs"]["capacity"], verified=False)}
            )
        )
    with pytest.raises((ValueError, RuntimeError)):
        await invoke(h)
    assert not h["state"]["sent"]


async def test_schema_repairs_share_three_actual_paid_attempts(harness):
    h = harness
    valid = h["state"]["responses"][0]
    h["state"]["responses"] = ["{}", "{}", valid]
    assert (await invoke(h)).mode == "SUMMARY"
    assert len(h["state"]["sent"]) == 3
    with sqlite3.connect(h["ledger"].path) as db:
        assert db.execute("SELECT attempts FROM execution_operations").fetchone() == (
            3,
        )
    assert h["ledger"].snapshot()["calls"] == 3


async def test_failed_derive_keeps_cost_and_unknown_reopen_cannot_send(harness):
    h = harness
    h["state"]["responses"] = ["{}"]
    with pytest.raises(ValueError):
        await invoke(h)
    assert len(h["state"]["sent"]) == 3
    assert h["ledger"].snapshot()["cost_microunits"] == 30
    with pytest.raises((ValueError, RuntimeError)):
        await invoke(h)
    assert len(h["state"]["sent"]) == 3


@pytest.mark.parametrize("status", [402, 429])
async def test_persistent_circuit_prevents_new_derive_send(harness, status):
    h = harness
    h["state"]["status"] = status
    client = h["kwargs"]["provider"].inner.client
    # 预先通过同一 PaidHttp 守卫制造已熔断预算；不绕过或另开授权。
    client._transport.require_context_guard = False
    for _ in range(1 if status == 402 else 2):
        await client.post(
            "https://fixture.test/chat/completions",
            json={"model": "fixture-model", "max_tokens": 500},
        )
    client._transport.require_context_guard = True
    before = len(h["state"]["sent"])
    with pytest.raises((ValueError, RuntimeError)):
        await invoke(h)
    assert len(h["state"]["sent"]) == before


async def test_arbitrary_fake_provider_cannot_be_marked_guarded(harness):
    h = harness

    class FakeProvider:
        paid_transport = True

    with pytest.raises(ValueError, match="GUARDED_PROVIDER_REQUIRED"):
        DeriveGateway(**(h["kwargs"] | {"provider": FakeProvider()}))


@pytest.mark.parametrize("mode", ["PROPOSALS", "BOTH"])
async def test_allowed_modes_return_single_pending_candidate(harness, mode):
    h = harness
    answer = json.loads(h["state"]["responses"][0])
    answer["mode"] = mode
    if mode == "PROPOSALS":
        answer["summary"] = None
    answer["proposals"] = [
        {"kind": "PREFERENCE", "field_key": "response.language", "value": "zh-CN"}
    ]
    h["state"]["responses"] = [json.dumps(answer)]
    candidate = await invoke(h, mode)
    assert candidate.mode == mode and candidate.proposals[0].value == "zh-CN"
    assert len(h["state"]["sent"]) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "fake-inner",
        "guard-off",
        "different-ledger",
        "unbound-counter",
        "no-live-validator",
    ],
)
async def test_guard_receipt_cannot_be_forged_by_provider_flags(
    harness, tmp_path, mutation
):
    h = harness
    provider = h["kwargs"]["provider"]
    if mutation == "fake-inner":
        provider.inner = object()
    elif mutation == "guard-off":
        provider.inner.client._transport.require_context_guard = False
    elif mutation == "different-ledger":
        from efficiency_platform_agent.persistence.paid_budget import (
            SqlitePaidBudgetLedger,
        )

        provider.inner.client._transport.ledger = SqlitePaidBudgetLedger(
            tmp_path / "other.sqlite"
        )
    elif mutation == "unbound-counter":
        provider.dispatch.controller._counter = ConservativeRequestTokenCounter()
    elif mutation == "no-live-validator":
        provider.dispatch.controller._validator = None
    with pytest.raises(ValueError, match="GUARDED_PROVIDER_REQUIRED"):
        DeriveGateway(**h["kwargs"])
    assert not h["state"]["sent"]


async def test_original_parent_close_cancels_inflight_derive(harness):
    import asyncio

    h = harness
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def blocked(request):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    h["kwargs"]["provider"].inner.client._transport.inner = httpx.MockTransport(blocked)
    parent = RunControl()
    with execution_scope(parent), paid_scope("original-parent"):
        task = asyncio.create_task(
            h["gateway"].derive(h["scope"], "SUMMARY", h["sources"], h["op"])
        )
    await entered.wait()
    await parent.close()
    try:
        assert cancelled.is_set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_network_unknown_retry_cannot_open_second_send_or_fresh_lease(harness):
    h = harness
    sent = []

    async def network_failure(request):
        sent.append(request)
        raise httpx.ReadError("synthetic network outcome unknown", request=request)

    inner = h["kwargs"]["provider"].inner
    inner.max_retries = 3
    inner.client._transport.inner = httpx.MockTransport(network_failure)
    with pytest.raises((ValueError, RuntimeError)):
        await invoke(h)
    assert len(sent) == 1
    with sqlite3.connect(h["ledger"].path) as db:
        attempts = db.execute("SELECT attempts FROM execution_operations").fetchone()[0]
        assert 1 <= attempts <= 3
        assert db.execute("SELECT state FROM derive_operations").fetchone() == (
            "UNKNOWN",
        )
    assert 1 <= h["ledger"].snapshot()["calls"] <= 3
    assert h["ledger"].snapshot()["cost_microunits"] >= 10
    with pytest.raises((ValueError, RuntimeError)):
        await invoke(h)
    assert len(sent) == 1


async def test_parent_stopped_while_paid_request_queued_sends_zero(harness):
    import asyncio

    h = harness
    parent = RunControl()
    slots = asyncio.Semaphore(0)
    h["kwargs"]["provider"].inner.client._transport.request_slots = slots
    with execution_scope(parent), paid_scope("original-parent"):
        task = asyncio.create_task(
            h["gateway"].derive(h["scope"], "SUMMARY", h["sources"], h["op"])
        )
    for _ in range(20):
        if slots._waiters:
            break
        await asyncio.sleep(0)
    parent.stop()
    slots.release()
    with pytest.raises((ValueError, RuntimeError)):
        await task
    assert not h["state"]["sent"] and h["ledger"].snapshot()["calls"] == 0


@pytest.mark.parametrize("kind", ["calls", "cost", "deadline"])
async def test_original_paid_remaining_limits_are_not_expanded(harness, kind):
    h = harness
    with sqlite3.connect(h["ledger"].path) as db:
        if kind == "calls":
            db.execute("UPDATE budgets SET calls=20")
        elif kind == "cost":
            db.execute("UPDATE budgets SET cost=100000")
        else:
            plan = json.loads(db.execute("SELECT plan FROM budgets").fetchone()[0])
            plan["deadline_epoch_ms"] = int(time.time() * 1000) - 1
            db.execute("UPDATE budgets SET plan=?", (json.dumps(plan),))
    with pytest.raises((ValueError, RuntimeError)):
        await invoke(h)
    assert not h["state"]["sent"]


@pytest.mark.parametrize(
    "mutation",
    ["summary-summary", "incomplete-tool-group", "proposal-permission-scope"],
)
async def test_invalid_original_source_group_is_rejected_before_hydration(
    harness, mutation
):
    h = harness
    selected = h["sources"][0]
    if mutation == "summary-summary":
        selected = selected.model_copy(update={"source_kind": "SUMMARY"})
    elif mutation == "incomplete-tool-group":
        extra = selected.source_ref.model_copy(
            update={"source_id": "missing-tool-result"}
        )
        selected = selected.model_copy(
            update={"group_members": (selected.source_ref, extra)}
        )
    else:
        selected = selected.model_copy(
            update={"proposals_scope_ref": "different-scope"}
        )
    with pytest.raises(ValueError):
        await invoke(
            h,
            "BOTH" if mutation == "proposal-permission-scope" else "SUMMARY",
            sources=(selected,),
        )
    assert h["state"]["checks"] == 0 and not h["state"]["sent"]


async def test_fake_dispatch_cannot_send_unmeasured_full_request(harness):
    h = harness
    counter = h["kwargs"]["counter"]
    real_dispatch = h["kwargs"]["provider"].dispatch

    class PermissiveSend:
        def __init__(self, request):
            self.prepared = SimpleNamespace(request=request)
            self.sent = False

        async def before_send(self, payload):
            self.sent = True

        def check_live(self):
            pass

        async def finish(self, succeeded):
            pass

    class FakeDispatch:
        authority = real_dispatch.authority
        stage_store = real_dispatch.stage_store
        controller = real_dispatch.controller
        store = real_dispatch.store

        def validate_key(self, key):
            pass

        async def prepare(self, request, provider_id, model):
            async def complete():
                pass

            stage = current_model_stage()
            assert stage is not None
            stage.complete = complete
            return PermissiveSend(request)

    h["kwargs"]["provider"].dispatch = FakeDispatch()
    try:
        with pytest.raises(ValueError, match="GUARDED_PROVIDER_REQUIRED"):
            h["gateway"] = DeriveGateway(
                **(h["kwargs"] | {"limits": WindowLimits(100000, 99000, 500, 100, 100)})
            )
            await invoke(h)
    finally:
        print(
            json.dumps(
                {
                    "upstream_wires": len(h["state"]["sent"]),
                    "full_measure_calls": counter.full_calls,
                    "fragment_measure_calls": counter.fragment_calls,
                }
            )
        )
    assert not h["state"]["sent"] and counter.full_calls == 0
    assert h["ledger"].snapshot()["calls"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "fake-controller",
        "different-store",
        "missing-store",
        "different-dispatch-authority",
    ],
)
async def test_context_chain_requires_real_controller_and_same_store(harness, mutation):
    h = harness
    dispatch = h["kwargs"]["provider"].dispatch
    if mutation == "fake-controller":
        dispatch.controller = SimpleNamespace(
            _counter=h["kwargs"]["counter"],
            _validator=dispatch.controller._validator,
            _store=dispatch.store,
        )
    elif mutation == "different-store":
        dispatch.store = object()
    elif mutation == "missing-store":
        dispatch.store = dispatch.controller._store = None
    elif mutation == "different-dispatch-authority":
        dispatch.authority = object()
    with pytest.raises(ValueError, match="GUARDED_PROVIDER_REQUIRED"):
        DeriveGateway(**h["kwargs"])
    assert not h["state"]["sent"] and h["ledger"].snapshot()["calls"] == 0


async def test_real_context_controller_measures_whole_schema_before_window_rejection(
    harness,
):
    h = harness
    h["gateway"] = DeriveGateway(
        **(h["kwargs"] | {"limits": WindowLimits(100000, 99000, 500, 100, 100)})
    )
    with pytest.raises(ValueError, match="CONTEXT_REQUIRED_INPUT_TOO_LARGE"):
        await invoke(h)
    counter = h["kwargs"]["counter"]
    assert counter.fragment_calls >= 1 and counter.full_calls >= 1
    assert h["state"]["checks"] >= 2
    assert not h["state"]["sent"] and h["ledger"].snapshot()["calls"] == 0
