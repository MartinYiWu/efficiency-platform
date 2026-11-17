"""最终持久门禁等待后不延长原截止、不越过停止信号发送。"""

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from efficiency_platform_agent.context.dispatch import (
    ControlledModelProvider,
    ControlledStreamingModelProvider,
)
from efficiency_platform_agent.core.context_dispatch import (
    bind_context_send_guard,
    model_stage,
)
from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.core.run import ProviderStreamChunk
from efficiency_platform_agent.providers import paid_http
from efficiency_platform_agent.providers.paid_http import (
    PaidBudgetTransportError,
    PaidHttpTransport,
)
from tests.unit.context.test_entrypoint_coverage import (
    FakeStages,
    Provider,
    configured,
    request,
)


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("event", ["deadline", "stop"])
async def test_cas_wait_rechecks_original_context_deadline_and_control(
    streaming, event
):
    now = [1]
    entered, release = asyncio.Event(), asyncio.Event()
    dispatch, _, store, _ = configured(stages=FakeStages())
    dispatch.controller._clock = lambda: now[0]
    original = store.mark_sending

    async def blocked_mark(manifest, operation):
        marked = await original(manifest, operation)
        entered.set()
        await release.wait()
        return marked

    store.mark_sending = blocked_mark

    class Streaming(Provider):
        async def stream(self, value):
            self.requests.append(value)
            yield ProviderStreamChunk(delta="unexpected", finish_reason="stop")

    inner = Streaming()
    provider_type = (
        ControlledStreamingModelProvider if streaming else ControlledModelProvider
    )
    provider = provider_type(inner, dispatch, "deepseek", "fake", paid_transport=False)
    control = RunControl()

    async def invoke():
        if streaming:
            return [chunk async for chunk in provider.stream(request())]
        return await provider.complete(request())

    with execution_scope(control), model_stage("operation", b"original"):
        task = asyncio.create_task(invoke())
        await asyncio.wait_for(entered.wait(), 1)
        assert next(iter(store.receipts.values())).status == "SENT"
        if event == "deadline":
            now[0] = 100
        else:
            control.stop()
        release.set()
        expected = ValueError if event == "deadline" else PaidBudgetError
        with pytest.raises(expected):
            await task
        assert next(iter(store.receipts.values())).status == "UNKNOWN"
        assert next(iter(dispatch.stage_store.rows.values()))[3] == "UNKNOWN"
        with pytest.raises(ValueError, match="CONTEXT_STAGE_BLOCKED"):
            await invoke()
    assert inner.requests == []
    assert len(store.receipts) == 1


@pytest.mark.parametrize("event", ["deadline", "stop", "ledger-revoked"])
async def test_paid_guard_wait_rechecks_original_reservation_and_control(
    monkeypatch, event
):
    now = [9.0]
    monkeypatch.setattr(paid_http.time, "time", lambda: now[0])
    entered, release = asyncio.Event(), asyncio.Event()
    wire = []

    class Ledger:
        revoked = False
        reservations = 0
        checks = 0
        finishes = 0

        def active_budget_id(self):
            return "offline"

        def reserve(self, *args, **kwargs):
            self.reservations += 1
            return SimpleNamespace(reservation_id="original", deadline_epoch_ms=10000)

        def check_live(self, reservation_id):
            assert reservation_id == "original"
            self.checks += 1
            if self.revoked:
                raise PaidBudgetError("PAID_BUDGET_STOPPED", "原预算已停止")

        def record_status(self, *args):
            pass

        def finish(self, reservation_id):
            assert reservation_id == "original"
            self.finishes += 1

    class Guard:
        async def before_send(self, payload):
            entered.set()
            await release.wait()

        def check_live(self):
            pass

    def upstream(value):
        wire.append(value)
        return httpx.Response(400)

    ledger = Ledger()
    control = RunControl()
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            ledger,
            httpx.MockTransport(upstream),
            "deepseek",
            require_context_guard=True,
        )
    ) as client:
        with execution_scope(control), bind_context_send_guard(Guard()):
            task = asyncio.create_task(
                client.post(
                    "https://offline.invalid/chat/completions",
                    json={"model": "fake", "max_tokens": 100},
                )
            )
            await asyncio.wait_for(entered.wait(), 1)
            assert ledger.reservations == 1
            if event == "deadline":
                now[0] = 11.0
            elif event == "stop":
                control.stop()
            else:
                ledger.revoked = True
            release.set()
            with pytest.raises(PaidBudgetTransportError):
                await task
    assert wire == []
    assert ledger.reservations == 1
    assert ledger.finishes == 1
    assert not control.http_tasks


async def test_paid_ledger_recheck_cannot_outlive_context_deadline():
    wire = []
    now = [1]
    dispatch, _, store, _ = configured()
    dispatch.controller._clock = lambda: now[0]

    class Ledger:
        def active_budget_id(self):
            return "offline"

        def reserve(self, *args, **kwargs):
            return SimpleNamespace(
                reservation_id="original", deadline_epoch_ms=9999999999999
            )

        def check_live(self, reservation_id):
            now[0] = 100

        def record_status(self, *args):
            pass

        def finish(self, *args):
            pass

    def upstream(value):
        wire.append(value)
        return httpx.Response(400)

    async with httpx.AsyncClient(
        transport=PaidHttpTransport(
            Ledger(),
            httpx.MockTransport(upstream),
            "deepseek",
            require_context_guard=True,
        )
    ) as client:

        class HttpProvider(Provider):
            async def complete(self, value):
                from efficiency_platform_agent.providers.llm.deepseek import (
                    _json_value,
                    _serialize_message,
                )

                await client.post(
                    "https://offline.invalid/chat/completions",
                    json={
                        "model": "fake",
                        "messages": [
                            _serialize_message(message, supports_developer_role=True)
                            for message in value.messages
                        ],
                        **_json_value(value.options),
                    },
                )
                return await super().complete(value)

        provider = ControlledModelProvider(
            HttpProvider(), dispatch, "deepseek", "fake", paid_transport=True
        )
        with pytest.raises(ValueError, match="CONTEXT_DEADLINE_EXCEEDED"):
            await provider.complete(request())
    assert wire == []
    assert next(iter(store.receipts.values())).status == "UNKNOWN"
