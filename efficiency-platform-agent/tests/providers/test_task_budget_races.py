import asyncio
import multiprocessing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from unit.persistence.test_task_authorization_chain import (
    binding,
    continuation,
    prepared,
    reserve,
)

from efficiency_platform_agent.context.dispatch import DispatchPlan, _Send
from efficiency_platform_agent.core.context_dispatch import bind_context_send_guard
from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.core.paid_budget import PaidBudgetError, paid_scope
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.providers.paid_http import PaidHttpTransport
from tests.unit.persistence.test_context_manifest import setup as setup  # noqa: PLC0414


def _compete(args):
    path, _bid, operation = args
    ledger = SqlitePaidBudgetLedger(Path(path), task_authorization_enabled=True)
    sent = []
    value = binding("new", operation)

    class Guard:
        def task_authorization_binding(self):
            return value

    async def fake_send(request):
        sent.append(True)
        return httpx.Response(200, content=b"{}", request=request)

    async def run():
        transport = PaidHttpTransport(
            ledger, httpx.MockTransport(fake_send), "embedding"
        )
        with (
            bind_context_send_guard(Guard()),
            execution_scope(RunControl()),
            paid_scope("new"),
        ):
            async with httpx.AsyncClient(transport=transport) as client:
                try:
                    await client.post("https://fake.invalid", json={"model": "model"})
                except (httpx.RequestError, PaidBudgetError) as error:
                    return len(sent), getattr(error, "code", "unexpected")
        return len(sent), None

    return asyncio.run(run())


def test_processes_share_last_task_call_through_fake_transport(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFICIENCY_TASK_AUTHORIZATION_ENABLED", "true")
    ledger, prices = prepared(tmp_path, http=True)
    result = ledger.reserve(
        "root",
        "old",
        "embedding",
        "model",
        1,
        0,
        input_tokens=1,
        reasoning_tokens=0,
        task_binding=binding(),
    )
    ledger.finish(result.reservation_id)
    ledger.stop("root", "test")
    request = replace(continuation(), max_total_http=2, max_input_tokens=100000)
    successor = ledger.authorize_task_continuation(request, prices, confirm=True)[
        "authorization_id"
    ]
    with multiprocessing.get_context("spawn").Pool(2) as pool:
        results = pool.map(
            _compete, [(str(ledger.path), successor, "op-" + str(i)) for i in range(2)]
        )
    assert sum(value[0] for value in results) == 1
    assert sorted(value[1] or "sent" for value in results) == [
        "TASK_BUDGET_EXHAUSTED",
        "sent",
    ]
    assert ledger.task_authorization_snapshot("task")["calls"] == 2
    assert ledger.task_authorization_snapshot("task")["cost_microunits"] == 20
    assert ledger.snapshot("root")["stopped"]


def test_old_authorization_never_switches_and_disabled_cannot_fall_back(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("EFFICIENCY_TASK_AUTHORIZATION_ENABLED", "true")
    ledger, prices = prepared(tmp_path)
    result = reserve(ledger, "root", binding())
    ledger.finish(result.reservation_id)
    ledger.stop("root", "test")
    successor = ledger.authorize_task_continuation(
        continuation(), prices, confirm=True
    )["authorization_id"]
    assert ledger.task_budget_id(binding(), successor) == "root"
    with pytest.raises(PaidBudgetError):
        ledger.check_execution("tenant", "old")
    monkeypatch.setenv("EFFICIENCY_TASK_AUTHORIZATION_ENABLED", "false")
    ledger = SqlitePaidBudgetLedger(ledger.path, task_authorization_enabled=False)
    with pytest.raises(PaidBudgetError) as caught:
        ledger.reserve(
            successor, "new", "fake", "model", 1, 1, input_tokens=1, reasoning_tokens=0
        )
    assert caught.value.code == "CONTINUATION_AUTH_UNSUPPORTED"


async def test_dispatch_operation_hash_survives_new_run_but_rejects_changed_content(
    setup,
):
    s = setup
    scope = replace(s["scope"], execution_id="successor")
    metadata = replace(s["metadata"], ctx_revision=1)
    operation = replace(s["operation"], deadline_epoch_seconds=200)
    successor = await s["prepare"](
        scope=scope,
        metadata=metadata,
        operation=operation,
        request_template=replace(s["request"], timeout_ms=2000),
        policy=replace(s["policy"], scope=scope),
        pieces=tuple(replace(piece, scope=scope) for piece in s["pieces"]),
    )
    dispatch = SimpleNamespace(controller=s["controller"])
    old_plan = DispatchPlan(
        s["scope"], s["policy"], s["pieces"], s["metadata"], s["operation"]
    )
    old = _Send(dispatch, old_plan, s["prepared"]).task_authorization_binding()
    new = _Send(
        dispatch,
        replace(old_plan, scope=scope, metadata=metadata, operation=operation),
        successor,
    ).task_authorization_binding()
    assert (
        successor.manifest.canonical_request_hmac
        != s["prepared"].manifest.canonical_request_hmac
    )
    assert old.operation_id == new.operation_id
    assert old.input_hash == new.input_hash
    changed = replace(
        successor,
        request=replace(
            successor.request,
            options=replace(successor.request.options, items=(("temperature", 1),)),
        ),
    )
    assert (
        _Send(dispatch, old_plan, changed).task_authorization_binding().input_hash
        != old.input_hash
    )
