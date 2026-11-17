"""HR原执行账本绑定完整可信身份；所有SQLite均是测试临时文件。"""

import asyncio
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from efficiency_platform_agent.core.execution_control import consume_http_attempt
from efficiency_platform_agent.core.memory import ConversationScope
from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.core.run_context_binding import bind_conversation_scope
from efficiency_platform_agent.harness.hr_factory import PersistentHrRunControlStore
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger


def actor(user="user-1"):
    return ConversationScope("tenant", user, "hr", "hr", "TASK_ONLY", None)


def state(path):
    with sqlite3.connect(path) as connection:
        run = connection.execute(
            "SELECT deadline,stopped,calls,operation_attempt_limit FROM execution_runs WHERE tenant='tenant' AND run='run'"
        ).fetchone()
        operations = connection.execute(
            "SELECT operation,input_hash,attempts FROM execution_operations WHERE tenant='tenant' AND run='run'"
        ).fetchall()
    return run, operations


async def test_other_actor_cannot_read_success_cache_or_cancel_owner(tmp_path):
    path = tmp_path / "fake.sqlite"
    store = PersistentHrRunControlStore(SqlitePaidBudgetLedger(path))
    calls = []

    async def work():
        consume_http_attempt()
        calls.append("provider")
        return {"result": "actor-one-only"}

    with bind_conversation_scope(actor()):
        original = await store.get("tenant", "run", maximum_attempts=2)
        result = await original.execute("operation", work)
        assert (
            await (await store.get("tenant", "run")).execute("operation", work)
            == result
        )
    before = state(path)
    with bind_conversation_scope(actor("user-2")):
        with pytest.raises(PaidBudgetError) as get_error:
            await store.get("tenant", "run")
        assert get_error.value.code == "HR_EXECUTION_SCOPE_CONFLICT"
        with pytest.raises(PaidBudgetError) as cancel_error:
            await store.cancel("tenant", "run")
        assert cancel_error.value.code == "HR_EXECUTION_SCOPE_CONFLICT"
    assert state(path) == before
    assert store.controls["tenant", "run"] is original
    assert calls == ["provider"]
    with bind_conversation_scope(actor()):
        await store.cancel("tenant", "run")
    assert state(path)[0][1] == "AGENT_TASK_STOPPED"


async def test_scope_ownership_and_unknown_no_resend_survive_restart(tmp_path):
    path = tmp_path / "fake.sqlite"
    first = PersistentHrRunControlStore(SqlitePaidBudgetLedger(path))
    with bind_conversation_scope(actor()):
        control = await first.get("tenant", "run")
        assert first.ledger.claim_execution_operation(
            "tenant", "run", "operation", "hash"
        )
    before = state(path)
    second = PersistentHrRunControlStore(SqlitePaidBudgetLedger(path))
    with (
        bind_conversation_scope(actor("user-2")),
        pytest.raises(PaidBudgetError, match="scope"),
    ):
        await second.get("tenant", "run")
    calls = []

    async def forbidden_work():
        calls.append("provider")

    with bind_conversation_scope(actor()):
        resumed = await second.get("tenant", "run")
        assert resumed.deadline_epoch_ms == control.deadline_epoch_ms
        resumed.results["hr-input:operation"] = "hash"
        with pytest.raises(PaidBudgetError) as error:
            await resumed.execute("operation", forbidden_work)
        assert error.value.code == "HR_OPERATION_ALREADY_SUBMITTED"
    assert calls == []
    assert state(path) == before


@pytest.mark.parametrize("first_scope,second_scope", [(actor(), None), (None, actor())])
async def test_legacy_and_scoped_calls_cannot_take_over_each_other(
    tmp_path, first_scope, second_scope
):
    store = PersistentHrRunControlStore(
        SqlitePaidBudgetLedger(tmp_path / "fake.sqlite")
    )
    with bind_conversation_scope(first_scope):
        original = await store.get("tenant", "run")
    with bind_conversation_scope(second_scope):
        with pytest.raises(PaidBudgetError) as error:
            await store.get("tenant", "run")
        assert error.value.code == "HR_EXECUTION_SCOPE_CONFLICT"
        with pytest.raises(PaidBudgetError):
            await store.cancel("tenant", "run")
    with bind_conversation_scope(first_scope):
        assert await store.get("tenant", "run") is original


def test_concurrent_different_actors_bind_only_one_original_scope(tmp_path):
    path = tmp_path / "fake.sqlite"
    SqlitePaidBudgetLedger(path)
    barrier = Barrier(2)

    def bind(user):
        store = PersistentHrRunControlStore(SqlitePaidBudgetLedger(path))
        barrier.wait()

        async def invoke():
            with bind_conversation_scope(actor(user)):
                return await store.get("tenant", "run")

        try:
            control = asyncio.run(invoke())
            return user, control.deadline_epoch_ms
        except PaidBudgetError as error:
            return user, error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(bind, ("User", "User ")))
    assert sum(type(value) is int for _, value in results) == 1
    assert sum(value == "HR_EXECUTION_SCOPE_CONFLICT" for _, value in results) == 1


async def test_full_scope_and_tenant_are_bound_before_cache_lookup(tmp_path):
    store = PersistentHrRunControlStore(
        SqlitePaidBudgetLedger(tmp_path / "fake.sqlite")
    )
    with bind_conversation_scope(actor()):
        await store.get("tenant", "run")
    for scope in (
        replace(actor(), user_id="User-1"),
        replace(actor(), session_kind="CONVERSATION", session_id="session"),
        replace(actor(), domain="operations", top_level_agent_id="operations"),
    ):
        with bind_conversation_scope(scope), pytest.raises(PaidBudgetError):
            await store.get("tenant", "run")
    with bind_conversation_scope(actor()), pytest.raises(PaidBudgetError):
        await store.get("other-tenant", "run")


async def test_additive_legacy_migration_preserves_deadline_and_counters(tmp_path):
    path = tmp_path / "legacy.sqlite"
    deadline = int(time.time() * 1000) + 600000
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE execution_runs(tenant TEXT,run TEXT,deadline INTEGER NOT NULL,stopped TEXT,calls INTEGER NOT NULL DEFAULT 0,operation_attempt_limit INTEGER NOT NULL DEFAULT 3,PRIMARY KEY(tenant,run))"
        )
        connection.execute(
            "INSERT INTO execution_runs VALUES('tenant','run',?,NULL,2,2)", (deadline,)
        )
    ledger = SqlitePaidBudgetLedger(path)
    assert (
        ledger.bind_execution("tenant", "run", 600000, maximum_attempts=3) == deadline
    )
    before = state(path)
    store = PersistentHrRunControlStore(ledger)
    with bind_conversation_scope(actor()), pytest.raises(PaidBudgetError):
        await store.get("tenant", "run")
    assert state(path) == before
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT context_identity FROM execution_runs"
        ).fetchone() == (None,)


async def test_same_actor_concurrent_stores_keep_one_attempt_and_original_deadline(
    tmp_path,
):
    path = tmp_path / "fake.sqlite"
    first = PersistentHrRunControlStore(SqlitePaidBudgetLedger(path))
    second = PersistentHrRunControlStore(SqlitePaidBudgetLedger(path))
    calls = []

    async def work():
        consume_http_attempt()
        calls.append("provider")
        await asyncio.sleep(0)
        return "success"

    with bind_conversation_scope(actor()):
        first_control = await first.get("tenant", "run", maximum_attempts=2)
        second_control = await second.get("tenant", "run", maximum_attempts=3)
        assert first_control.deadline_epoch_ms == second_control.deadline_epoch_ms
        results = await asyncio.gather(
            first_control.execute("operation", work),
            second_control.execute("operation", work),
            return_exceptions=True,
        )
    assert sum(value == "success" for value in results) == 1
    assert (
        sum(
            isinstance(value, PaidBudgetError)
            and value.code == "HR_OPERATION_ALREADY_SUBMITTED"
            for value in results
        )
        == 1
    )
    assert calls == ["provider"]
    assert state(path)[0][2:] == (1, 2)
    assert state(path)[1][0][2] == 1
    await first.close()
    assert state(path)[0][1] == "AGENT_TASK_STOPPED"


async def test_stopped_bound_run_rejects_other_actor_before_revealing_stop_state(
    tmp_path,
):
    path = tmp_path / "fake.sqlite"
    store = PersistentHrRunControlStore(SqlitePaidBudgetLedger(path))
    with bind_conversation_scope(actor()):
        await store.get("tenant", "run")
        await store.cancel("tenant", "run")
    before = state(path)
    with (
        bind_conversation_scope(actor("other")),
        pytest.raises(PaidBudgetError) as error,
    ):
        await PersistentHrRunControlStore(SqlitePaidBudgetLedger(path)).get(
            "tenant", "run"
        )
    assert error.value.code == "HR_EXECUTION_SCOPE_CONFLICT"
    assert state(path) == before
