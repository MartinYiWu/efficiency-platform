from dataclasses import replace

import pytest

from efficiency_platform_agent.core.paid_budget import (
    PaidBudgetError,
    PaidBudgetPlan,
    PaidPriceLimit,
    PaidUsage,
)
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger


def plan(**kw):
    p = PaidBudgetPlan(
        "b",
        20,
        1000,
        9999999999999,
        20,
        1000,
        999999999,
        20,
        2,
        100,
        100,
        100,
        100,
        100,
        100,
    )
    return replace(p, **kw)


def price():
    return (
        PaidPriceLimit(
            "p", "m", 1000, 20, 100, "manual", "v1", 20, 1000000, 500000, 2000000
        ),
    )


def reserve(l, **kw):
    return l.reserve(
        None,
        kw.pop("scope", "s"),
        "p",
        "m",
        10,
        kw.pop("out", 5),
        input_tokens=kw.pop("inp", 10),
        reasoning_tokens=kw.pop("reason", 0),
    )


def test_settle_releases_only_confirmed_unused(tmp_path):
    l = SqlitePaidBudgetLedger(tmp_path / "a.db")
    l.authorize(plan(), price())
    r = reserve(l, reason=2)
    l.record_status(r.reservation_id, 200)
    l.settle(r.reservation_id, PaidUsage(4, 2, 2, 1))
    l.settle(r.reservation_id, PaidUsage(4, 2, 2, 1))
    l.finish(r.reservation_id)
    assert l.snapshot()["cost_microunits"] == 7
    assert l.snapshot()["accounting"]["effective_tokens"]["input_tokens"] == 4
    with pytest.raises(PaidBudgetError):
        l.settle(r.reservation_id, PaidUsage(5, 2))


@pytest.mark.parametrize(
    "field,kwargs",
    [
        ("max_input_tokens", {"inp": 11}),
        ("max_output_tokens", {"out": 11}),
        ("max_reasoning_tokens", {"out": 11, "reason": 11}),
    ],
)
def test_total_token_cap(tmp_path, field, kwargs):
    l = SqlitePaidBudgetLedger(tmp_path / "a.db")
    l.authorize(plan(**{field: 10}), price())
    with pytest.raises(PaidBudgetError):
        reserve(l, **kwargs)
    assert l.snapshot()["calls"] == 0


def test_unknown_finish_keeps_hold(tmp_path):
    l = SqlitePaidBudgetLedger(tmp_path / "a.db")
    l.authorize(plan(), price())
    r = reserve(l)
    l.finish(r.reservation_id)
    assert l.snapshot()["cost_microunits"] == 100
    assert l.details()["attempts"][0]["state"] == "unknown"
    with pytest.raises(PaidBudgetError):
        l.settle(r.reservation_id, PaidUsage(1, 1))


def test_overrun_records_actual_and_stops(tmp_path):
    l = SqlitePaidBudgetLedger(tmp_path / "a.db")
    l.authorize(plan(), price())
    r = reserve(l)
    l.record_status(r.reservation_id, 200)
    with pytest.raises(PaidBudgetError):
        l.settle(r.reservation_id, PaidUsage(200, 5))
    assert l.snapshot()["stopped"] == "usage_exceeded"
    assert l.details()["attempts"][0]["reported_cost_microunits"] == 210
    assert l.snapshot()["cost_microunits"] == 210


def test_old_authorization_rejected(tmp_path):
    l = SqlitePaidBudgetLedger(tmp_path / "a.db")
    with pytest.raises(PaidBudgetError):
        l.authorize(replace(plan(), max_input_tokens=0), price())


@pytest.mark.parametrize(
    "dimension,kwargs",
    [
        ("input", {"inp": 6}),
        ("output", {"out": 6}),
        ("reasoning", {"out": 6, "reason": 6}),
    ],
)
def test_scope_token_cap(tmp_path, dimension, kwargs):
    l = SqlitePaidBudgetLedger(tmp_path / "a.db")
    l.authorize(plan(**{"max_run_" + dimension + "_tokens": 10}), price())
    r = reserve(l, **kwargs)
    l.finish(r.reservation_id)
    with pytest.raises(PaidBudgetError):
        reserve(l, **kwargs)
    reserve(l, scope="other", **kwargs)


def test_price_is_frozen_and_finish_before_settle_rejects(tmp_path):
    import sqlite3

    l = SqlitePaidBudgetLedger(tmp_path / "a.db")
    l.authorize(plan(), price())
    r = reserve(l)
    with sqlite3.connect(l.path) as c:
        c.execute(
            "UPDATE prices SET pricing=json_set(pricing,'$.input_microunits_per_million',9000000)"
        )
    l.record_status(r.reservation_id, 200)
    l.settle(r.reservation_id, PaidUsage(4, 2))
    assert l.details()["attempts"][0]["reported_cost_microunits"] == 8
    l.finish(r.reservation_id)
    r = reserve(l)
    l.record_status(r.reservation_id, 200)
    l.finish(r.reservation_id)
    with pytest.raises(PaidBudgetError):
        l.settle(r.reservation_id, PaidUsage(1, 1))


def test_migrate_legacy_preserves_money_and_refuses_spend(tmp_path):
    import json
    import sqlite3
    from dataclasses import asdict

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as c:
        c.executescript(
            "CREATE TABLE budgets(id TEXT PRIMARY KEY,plan TEXT,calls INTEGER DEFAULT 0,cost INTEGER DEFAULT 0,run_calls INTEGER DEFAULT 0,run_cost INTEGER DEFAULT 0,inflight INTEGER DEFAULT 0,stopped TEXT,r429 INTEGER DEFAULT 0,first_ms INTEGER);CREATE TABLE prices(bid TEXT,provider TEXT,model TEXT,req INTEGER,out INTEGER,cost INTEGER,src TEXT,PRIMARY KEY(bid,provider,model));CREATE TABLE reservations(id TEXT PRIMARY KEY,bid TEXT,scope TEXT,deadline INTEGER,active INTEGER DEFAULT 1,status INTEGER);"
        )
        old = {k: v for k, v in asdict(plan()).items() if "tokens" not in k}
        c.execute(
            "INSERT INTO budgets(id,plan,calls,cost) VALUES (?,?,?,?)",
            ("b", json.dumps(old), 2, 87),
        )
        c.execute("INSERT INTO prices VALUES ('b','p','m',1000,20,100,'old')")
        c.execute("INSERT INTO reservations VALUES ('r','b','s',9999999999999,0,200)")
    l = SqlitePaidBudgetLedger(path)
    assert l.snapshot()["cost_microunits"] == 87
    assert l.details()["attempts"][0]["state"] == "legacy"
    with pytest.raises(PaidBudgetError):
        reserve(l)
    assert l.snapshot()["cost_microunits"] == 87


def test_stop_does_not_refund_success(tmp_path):
    l = SqlitePaidBudgetLedger(tmp_path / "a.db")
    l.authorize(plan(), price())
    r = reserve(l)
    l.record_status(r.reservation_id, 200)
    l.stop("b", "stop")
    with pytest.raises(PaidBudgetError):
        l.settle(r.reservation_id, PaidUsage(1, 1))
    assert l.snapshot()["cost_microunits"] == 100


def token_attempt(args):
    path, i = args
    l = SqlitePaidBudgetLedger(path)
    try:
        r = reserve(l, scope=str(i), inp=10)
        l.finish(r.reservation_id)
        return True
    except PaidBudgetError:
        return False


def test_processes_share_token_total(tmp_path):
    import multiprocessing

    path = tmp_path / "atomic.db"
    l = SqlitePaidBudgetLedger(path)
    l.authorize(plan(max_input_tokens=20), price())
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        results = pool.map(token_attempt, [(path, i) for i in range(8)])
    assert sum(results) == 2
    assert l.snapshot()["accounting"]["effective_tokens"]["input_tokens"] == 20


def test_concurrent_identical_settle_only_refunds_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "a.db"
    l = SqlitePaidBudgetLedger(path)
    l.authorize(plan(), price())
    r = reserve(l)
    l.record_status(r.reservation_id, 200)

    def settle(_):
        SqlitePaidBudgetLedger(path).settle(r.reservation_id, PaidUsage(4, 2))

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(settle, range(8)))
    assert l.snapshot()["cost_microunits"] == 8
    assert l.snapshot()["calls"] == 1


def initialize_legacy(path):
    return SqlitePaidBudgetLedger(path).snapshot()["cost_microunits"]


def test_processes_migrate_same_legacy_schema(tmp_path):
    import json
    import multiprocessing
    import sqlite3
    from dataclasses import asdict

    path = tmp_path / "legacy-parallel.db"
    with sqlite3.connect(path) as c:
        c.executescript(
            "CREATE TABLE budgets(id TEXT PRIMARY KEY,plan TEXT,calls INTEGER DEFAULT 0,cost INTEGER DEFAULT 0,run_calls INTEGER DEFAULT 0,run_cost INTEGER DEFAULT 0,inflight INTEGER DEFAULT 0,stopped TEXT,r429 INTEGER DEFAULT 0,first_ms INTEGER);CREATE TABLE prices(bid TEXT,provider TEXT,model TEXT,req INTEGER,out INTEGER,cost INTEGER,src TEXT,PRIMARY KEY(bid,provider,model));CREATE TABLE reservations(id TEXT PRIMARY KEY,bid TEXT,scope TEXT,deadline INTEGER,active INTEGER DEFAULT 1,status INTEGER);"
        )
        old = {k: v for k, v in asdict(plan()).items() if "tokens" not in k}
        c.execute(
            "INSERT INTO budgets(id,plan,calls,cost) VALUES (?,?,?,?)",
            ("b", json.dumps(old), 2, 87),
        )
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        assert pool.map(initialize_legacy, [path] * 8) == [87] * 8
    assert (
        SqlitePaidBudgetLedger(path).snapshot()["accounting"]["held_cost_microunits"]
        == 87
    )


def test_snapshot_reports_one_database_revision_during_settle(tmp_path, monkeypatch):
    import sqlite3

    path = tmp_path / "report.db"
    l = SqlitePaidBudgetLedger(path)
    l.authorize(plan(), price())
    r = reserve(l)
    l.record_status(r.reservation_id, 200)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    settled = False

    class RacingConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            nonlocal settled
            if sql.startswith("SELECT provider,model,req") and not settled:
                settled = True
                SqlitePaidBudgetLedger(path).settle(r.reservation_id, PaidUsage(4, 2))
            return super().execute(sql, parameters)

    monkeypatch.setattr(
        l,
        "_db",
        lambda: sqlite3.connect(path, isolation_level=None, factory=RacingConnection),
    )
    report = l.snapshot()
    assert settled
    assert report["cost_microunits"] == 100
    assert report["accounting"]["actual_cost_microunits"] == 0
    assert report["accounting"]["held_cost_microunits"] == 100
    scope = report["scopes"][0]
    assert (
        scope["cost_microunits"]
        == scope["accounting"]["actual_cost_microunits"]
        + scope["accounting"]["held_cost_microunits"]
    )


def test_legacy_scope_money_remains_an_unknown_hold(tmp_path):
    import sqlite3

    l = SqlitePaidBudgetLedger(tmp_path / "legacy-scope.db")
    l.authorize(plan(), price())
    with sqlite3.connect(l.path) as c:
        c.execute(
            "INSERT INTO scopes(bid,scope,calls,cost,deadline) VALUES ('b','legacy',2,87,9999999999999)"
        )
        c.execute("UPDATE budgets SET calls=2,cost=87 WHERE id='b'")
        c.execute(
            "INSERT INTO reservations(id,bid,scope,deadline,active) VALUES ('old','b','legacy',9999999999999,0)"
        )
    scope = l.snapshot()["scopes"][0]
    assert scope["accounting"]["actual_cost_microunits"] == 0
    assert scope["accounting"]["held_cost_microunits"] == 87


def test_reported_cost_overflow_is_persistently_stopped_and_exact(tmp_path):
    import sqlite3

    path = tmp_path / "overflow.db"
    l = SqlitePaidBudgetLedger(path)
    costly = (
        replace(
            price()[0],
            max_input_tokens=1,
            max_output_tokens=0,
            input_microunits_per_million=10**12,
            cached_input_microunits_per_million=0,
            max_cost_microunits_per_attempt=10**6,
        ),
    )
    l.authorize(
        plan(max_cost_microunits=10**14, max_run_cost_microunits=10**14), costly
    )
    r = reserve(l, inp=1, out=0)
    l.record_status(r.reservation_id, 200)
    usage = PaidUsage(2**63 - 1, 0)
    expected = ((2**63 - 1) * 10**12 + 999999) // 1000000
    with pytest.raises(PaidBudgetError):
        l.settle(r.reservation_id, usage)
    reopened = SqlitePaidBudgetLedger(path)
    assert reopened.snapshot()["stopped"] == "usage_overflow"
    assert reopened.details()["attempts"][0]["reported_cost_microunits"] == expected
    assert reopened.details()["attempts"][0]["reported_usage"] == usage.__dict__
    assert reopened.snapshot()["accounting"]["actual_cost_microunits"] == expected
    assert reopened.snapshot()["accounting"]["cost_overflow"] is True
    assert reopened.snapshot()["remaining_cost_microunits"] == 0
    with sqlite3.connect(path) as c:
        raw = c.execute(
            "SELECT actual_cost_decimal,typeof(actual_cost_decimal) FROM reservations"
        ).fetchone()
    assert raw == (str(expected), "text")
    with pytest.raises(PaidBudgetError):
        reserve(reopened, inp=1, out=0)


def test_actual_cost_aggregate_overflow_does_not_become_sqlite_real(tmp_path):
    import sqlite3

    path = tmp_path / "sum-overflow.db"
    l = SqlitePaidBudgetLedger(path)
    l.authorize(plan(), price())
    r = reserve(l)
    l.record_status(r.reservation_id, 200)
    with sqlite3.connect(path) as c:
        c.execute("UPDATE budgets SET cost=?,run_cost=?", (2**63 - 2, 2**63 - 2))
        c.execute("UPDATE scopes SET cost=?", (2**63 - 2,))
    with pytest.raises(PaidBudgetError):
        l.settle(r.reservation_id, PaidUsage(200, 5))
    assert l.snapshot()["stopped"] == "usage_overflow"
    assert l.snapshot()["accounting"]["actual_cost_microunits"] == 210
    assert l.snapshot()["remaining_cost_microunits"] == 0
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT cost,typeof(cost) FROM budgets").fetchone() == (
            2**63 - 2,
            "integer",
        )
    assert l.snapshot()["scopes"][0]["accounting"]["cost_overflow"] is True


def test_overflow_preserves_other_unknown_cost_hold(tmp_path):
    path = tmp_path / "overflow-holds.db"
    l = SqlitePaidBudgetLedger(path)
    costly = (
        replace(
            price()[0],
            max_input_tokens=1,
            max_output_tokens=0,
            input_microunits_per_million=10**12,
            cached_input_microunits_per_million=0,
            max_cost_microunits_per_attempt=10**6,
        ),
    )
    l.authorize(
        plan(max_cost_microunits=10**14, max_run_cost_microunits=10**14), costly
    )
    unknown = reserve(l, inp=1, out=0)
    l.finish(unknown.reservation_id)
    overflowing = reserve(l, inp=1, out=0)
    l.record_status(overflowing.reservation_id, 200)
    with pytest.raises(PaidBudgetError):
        l.settle(overflowing.reservation_id, PaidUsage(2**63 - 1, 0))
    report = l.snapshot()
    assert report["accounting"]["held_cost_microunits"] == 10**6
    assert report["scopes"][0]["accounting"]["held_cost_microunits"] == 10**6
    assert report["accounting"]["unknown_attempts"] == 1
    assert report["remaining_cost_microunits"] == 0
