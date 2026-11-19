import sqlite3
import time
from dataclasses import replace

import pytest

from efficiency_platform_agent.core.memory import ConversationScope, ExecutionScope
from efficiency_platform_agent.core.paid_budget import (
    PaidBudgetError,
    PaidBudgetPlan,
    PaidPriceLimit,
)
from efficiency_platform_agent.core.task_authorization import (
    TaskContinuation,
    TaskPaidBinding,
)
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger


def prepared(tmp_path, *, http=False, enabled=True):
    ledger = SqlitePaidBudgetLedger(
        tmp_path / "fake.sqlite3", task_authorization_enabled=enabled
    )
    ledger.initialize_task_authorization_schema(tmp_path / "before.sqlite3")
    plan = PaidBudgetPlan(
        "root",
        4,
        40,
        int(time.time() * 1000) + 60000,
        4,
        40,
        60000,
        2,
        2,
        1000,
        1000,
        1000,
        1000,
        1000,
        1000,
    )
    prices = (
        PaidPriceLimit(
            "fake", "model", 100, 10, 10, "test", "v1", 100, 1000, 500, 1000
        ),
    )
    if http:
        plan = replace(plan, max_input_tokens=100000, max_run_input_tokens=100000)
        prices = (
            PaidPriceLimit(
                "embedding", "model", 10000, 10, 10, "test", "v1", 20000, 1, 0, 1
            ),
        )
    ledger.authorize(plan, prices)
    return ledger, prices


def binding(run="old", operation="op"):
    conversation = ConversationScope("tenant", "user", "hr", "hr", "TASK_ONLY", None)
    return TaskPaidBinding(
        ExecutionScope(conversation, "task", run, "step", "answer", "hr"),
        operation,
        "input",
    )


def reserve(ledger, bid, value):
    return ledger.reserve(
        bid,
        value.scope.execution_id,
        "fake",
        "model",
        1,
        1,
        input_tokens=1,
        reasoning_tokens=0,
        task_binding=value,
    )


def continuation():
    return TaskContinuation(
        "task", "root", 40, 4, 1000, 1000, 1000, int(time.time() * 1000) + 60000
    )


def test_chain_preserves_unknown_limits_attempts_and_idempotence(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFICIENCY_TASK_AUTHORIZATION_ENABLED", "true")
    ledger, prices = prepared(tmp_path)
    for _ in range(2):
        result = reserve(ledger, "root", binding())
        ledger.finish(result.reservation_id)
    ledger.stop("root", "test")
    request = continuation()
    preview = ledger.authorize_task_continuation(request, prices, confirm=False)
    assert ledger.active_budget_id() == "root"
    created = ledger.authorize_task_continuation(request, prices, confirm=True)
    assert preview["authorization_id"] == created["authorization_id"]
    assert ledger.authorize_task_continuation(request, prices, confirm=True) == created
    reserve(ledger, created["authorization_id"], binding("new"))
    with pytest.raises(PaidBudgetError, match="operation attempts"):
        reserve(ledger, created["authorization_id"], binding("new"))
    assert ledger.task_authorization_snapshot("task")["calls"] == 3
    assert ledger.task_authorization_snapshot("task")["cost_microunits"] == 30
    assert ledger.snapshot("root")["stopped"]
    with pytest.raises(PaidBudgetError):
        reserve(ledger, "root", binding())


def test_chain_cannot_bypass_provider_breaker(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFICIENCY_TASK_AUTHORIZATION_ENABLED", "true")
    ledger, prices = prepared(tmp_path)
    reservation = reserve(ledger, "root", binding())
    ledger.record_status(reservation.reservation_id, 402)
    ledger.finish(reservation.reservation_id)
    with pytest.raises(PaidBudgetError) as caught:
        ledger.authorize_task_continuation(continuation(), prices, confirm=True)
    assert caught.value.code == "PROVIDER_CIRCUIT_OPEN"


def test_default_schema_unchanged_and_continuation_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("EFFICIENCY_TASK_AUTHORIZATION_ENABLED", raising=False)
    ledger, prices = prepared(tmp_path, enabled=False)
    with pytest.raises(PaidBudgetError) as caught:
        ledger.authorize_task_continuation(continuation(), prices, confirm=True)
    assert caught.value.code == "CONTINUATION_AUTH_UNSUPPORTED"
    untouched = tmp_path / "legacy.sqlite3"
    SqlitePaidBudgetLedger(untouched)
    with sqlite3.connect(untouched) as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE 'task_%'"
            ).fetchall()
            == []
        )


def test_continuation_keeps_stricter_operation_limit_and_cumulative_429(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("EFFICIENCY_TASK_AUTHORIZATION_ENABLED", "true")
    ledger, prices = prepared(tmp_path)
    ledger.bind_execution(
        "tenant",
        "old",
        60000,
        maximum_attempts=1,
        context_scope=binding().scope.conversation,
    )
    first = reserve(ledger, "root", binding())
    ledger.record_status(first.reservation_id, 429)
    ledger.finish(first.reservation_id)
    ledger.stop("root", "test")
    child = ledger.authorize_task_continuation(continuation(), prices, confirm=True)[
        "authorization_id"
    ]
    with pytest.raises(PaidBudgetError) as caught:
        reserve(ledger, child, binding("new"))
    assert caught.value.code == "AGENT_OPERATION_ATTEMPTS_EXHAUSTED"
    second = reserve(ledger, child, binding("new", "other"))
    ledger.record_status(second.reservation_id, 429)
    ledger.finish(second.reservation_id)
    with pytest.raises(PaidBudgetError) as caught:
        ledger.authorize_task_continuation(
            replace(continuation(), continuation_of=child), prices, confirm=True
        )
    assert caught.value.code == "PROVIDER_CIRCUIT_OPEN"
