from pathlib import Path

from efficiency_platform_agent.core.paid_budget import *
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger


def lim():
    return (PaidPriceLimit("p", "m", 100, 10, 5, "manual", "v1", 100, 1000, 500, 1000),)


def plan():
    return PaidBudgetPlan(
        "b",
        2,
        10,
        9999999999999,
        2,
        10,
        999999999999,
        1,
        1,
        1000,
        1000,
        0,
        1000,
        1000,
        0,
    )


def test_ledger(tmp_path):
    l = SqlitePaidBudgetLedger(tmp_path / "x.db")
    l.authorize(plan(), lim())
    r = l.reserve(None, "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    l.record_status(r.reservation_id, 402)
    try:
        l.reserve(None, "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
        assert False
    except PaidBudgetError as e:
        assert e.code == "BUDGET_STOPPED"


import multiprocessing
from dataclasses import replace

import pytest


def attempt(args):
    path, i = args
    l = SqlitePaidBudgetLedger(Path(path))
    try:
        r = l.reserve("b", str(i), "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
        l.finish(r.reservation_id)
        return True
    except PaidBudgetError:
        return False


def test_atomic_processes(tmp_path):
    path = tmp_path / "p.db"
    l = SqlitePaidBudgetLedger(path)
    l.authorize(replace(plan(), max_inflight=20), lim())
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        results = pool.map(attempt, [(str(path), i) for i in range(8)])
    assert sum(results) == 2
    assert l.snapshot()["cost_microunits"] == 10


def test_reopen_and_finish_idempotent(tmp_path):
    path = tmp_path / "x.db"
    l = SqlitePaidBudgetLedger(path)
    l.authorize(plan(), lim())
    r = l.reserve(None, "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    l.finish(r.reservation_id)
    l.finish(r.reservation_id)
    l = SqlitePaidBudgetLedger(path)
    assert l.snapshot()["calls"] == 1
    assert l.snapshot()["inflight"] == 0
    with pytest.raises(PaidBudgetError):
        l.authorize(plan(), lim())


def test_rejected_payload_and_unknown_price_no_charge(tmp_path):
    l = SqlitePaidBudgetLedger(tmp_path / "x.db")
    l.authorize(plan(), lim())
    for model, size, out in [
        ("unknown", 1, 1),
        ("m", 101, 1),
        ("m", 1, 11),
        ("m", -1, 1),
        ("m", 1, True),
    ]:
        with pytest.raises(PaidBudgetError):
            l.reserve(
                None, "s", "p", model, size, out, input_tokens=1, reasoning_tokens=0
            )
    assert l.snapshot()["calls"] == 0


def test_scope_and_concurrency(tmp_path):
    l = SqlitePaidBudgetLedger(tmp_path / "x.db")
    l.authorize(
        replace(plan(), max_calls=8, max_cost_microunits=100, max_run_calls=1), lim()
    )
    r = l.reserve(None, "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    with pytest.raises(PaidBudgetError):
        l.reserve(None, "other", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    l.finish(r.reservation_id)
    with pytest.raises(PaidBudgetError):
        l.reserve(None, "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    l.reserve(None, "other", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)


def test_429_persistent_and_live(tmp_path):
    path = tmp_path / "x.db"
    l = SqlitePaidBudgetLedger(path)
    l.authorize(plan(), lim())
    r = l.reserve(None, "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    l.record_status(r.reservation_id, 429)
    reopened = SqlitePaidBudgetLedger(path)
    with pytest.raises(PaidBudgetError):
        reopened.check_live(r.reservation_id)
    assert reopened.snapshot()["429_responses"] == 1


def test_deadline_persisted(tmp_path, monkeypatch):
    import efficiency_platform_agent.persistence.paid_budget as module

    monkeypatch.setattr(module.time, "time", lambda: 100)
    l = SqlitePaidBudgetLedger(tmp_path / "x.db")
    l.authorize(replace(plan(), max_run_duration_ms=100), lim())
    r = l.reserve(None, "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    l.finish(r.reservation_id)
    monkeypatch.setattr(module.time, "time", lambda: 101)
    with pytest.raises(PaidBudgetError):
        l.reserve(None, "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)


def test_no_budget_and_broken_db(tmp_path):
    path = tmp_path / "x.db"
    l = SqlitePaidBudgetLedger(path)
    with pytest.raises(PaidBudgetError):
        l.reserve(None, "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    path.write_bytes(b"bad sqlite")
    with pytest.raises(PaidBudgetError, match="ledger unavailable"):
        l.active_budget_id()


def test_read_only_and_zero_authorization(tmp_path):
    path = tmp_path / "x.db"
    l = SqlitePaidBudgetLedger(path)
    with pytest.raises(PaidBudgetError):
        l.authorize(replace(plan(), max_calls=0), lim())
    l.authorize(plan(), lim())
    before = path.read_bytes()
    assert SqlitePaidBudgetLedger(path, read_only=True).snapshot()["calls"] == 0
    assert before == path.read_bytes()


def test_amount_is_prepaid_and_pending_is_retained(tmp_path):
    path = tmp_path / "x.db"
    l = SqlitePaidBudgetLedger(path)
    l.authorize(plan(), lim())
    l.reserve(None, "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    l = SqlitePaidBudgetLedger(path)
    assert l.snapshot()["cost_microunits"] == 5
    with pytest.raises(PaidBudgetError):
        l.reserve(None, "other", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    assert l.snapshot()["calls"] == 1


def test_switch_does_not_clear_pending_or_old_id(tmp_path):
    l = SqlitePaidBudgetLedger(tmp_path / "x.db")
    l.authorize(plan(), lim())
    r = l.reserve("b", "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    l.authorize(replace(plan(), budget_id="new"), lim())
    with pytest.raises(PaidBudgetError):
        l.reserve("new", "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    l.finish(r.reservation_id)
    assert l.active_budget_id() == "new"
    assert l.snapshot("b")["calls"] == 1


def test_429_accumulates_across_successes_and_instances(tmp_path):
    path = tmp_path / "x.db"
    l = SqlitePaidBudgetLedger(path)
    l.authorize(
        replace(
            plan(),
            max_calls=8,
            max_cost_microunits=100,
            max_run_calls=8,
            max_run_cost_microunits=100,
            max_429_responses=2,
        ),
        lim(),
    )
    for status in [429, 200, 429]:
        l = SqlitePaidBudgetLedger(path)
        r = l.reserve("b", "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
        l.record_status(r.reservation_id, status)
        l.finish(r.reservation_id)
    assert l.snapshot()["429_responses"] == 2
    with pytest.raises(PaidBudgetError):
        l.reserve("b", "new", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)


def test_new_authorization_supersedes_old_and_live(tmp_path):
    l = SqlitePaidBudgetLedger(tmp_path / "x.db")
    l.authorize(plan(), lim())
    r = l.reserve("b", "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    l.authorize(replace(plan(), budget_id="new"), lim())
    with pytest.raises(PaidBudgetError):
        l.check_live(r.reservation_id)
    l.finish(r.reservation_id)
    with pytest.raises(PaidBudgetError):
        l.reserve("b", "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    assert l.snapshot("b")["stopped"] == "superseded"


def test_status_repeated_is_idempotent(tmp_path):
    l = SqlitePaidBudgetLedger(tmp_path / "x.db")
    l.authorize(replace(plan(), max_429_responses=2), lim())
    r = l.reserve(None, "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    l.record_status(r.reservation_id, 429)
    l.record_status(r.reservation_id, 429)
    assert l.snapshot()["429_responses"] == 1
    l.check_live(r.reservation_id)


def test_snapshot_exposes_reviewable_limits(tmp_path):
    l = SqlitePaidBudgetLedger(tmp_path / "x.db")
    l.authorize(plan(), lim())
    l.reserve(None, "s", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    s = l.snapshot()
    assert s["limits"]["max_calls"] == 2
    assert s["remaining_calls"] == 1
    assert s["remaining_cost_microunits"] == 5
    assert s["deadline_epoch_ms"] == plan().deadline_epoch_ms
    assert s["prices"][0]["max_cost_microunits_per_attempt"] == 5
