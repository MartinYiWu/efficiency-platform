"""只使用临时既有付费总账，不授予真实额度。"""

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from efficiency_platform_agent.core.derive_ports import DeriveOperation
from efficiency_platform_agent.core.memory import ConversationScope, ExecutionScope
from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.persistence.derive_operation import (
    SqliteDeriveOperationStore,
)
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger


def setup_store(tmp_path):
    ledger = SqlitePaidBudgetLedger(tmp_path / "paid.sqlite")
    conversation = ConversationScope(
        "t", "u", "operations", "operations", "CONVERSATION", "s"
    )
    deadline = ledger.bind_execution("t", "run", 60000, context_scope=conversation)
    scope = ExecutionScope(conversation, "task", "exec", "sub", "derive", "operations")
    op = DeriveOperation(
        scope, "run", "original-op", "auth", "budget", deadline // 1000
    )
    store = SqliteDeriveOperationStore(ledger)
    store.initialize()
    return ledger, store, op


def test_unique_task_opportunity_is_atomic_across_connections(tmp_path):
    ledger, _, op = setup_store(tmp_path)

    def claim(_):
        try:
            return SqliteDeriveOperationStore(ledger).claim(op, "fingerprint").token
        except PaidBudgetError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(claim, range(8)))
    assert outcomes.count("DERIVE_OPPORTUNITY_BLOCKED") == 7
    assert len(set(outcomes)) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "another-run"),
        ("operation_id", "new-op"),
        ("authorization_ref", "new-auth"),
        ("budget_id", "new-budget"),
    ],
)
def test_new_binding_cannot_expand_consumed_task_opportunity(tmp_path, field, value):
    ledger, store, op = setup_store(tmp_path)
    store.claim(op, "fingerprint")
    if field == "run_id":
        ledger.bind_execution("t", value, 60000, context_scope=op.scope.conversation)
    with pytest.raises(PaidBudgetError):
        store.claim(replace(op, **{field: value}), "fingerprint")


def test_unknown_and_unfinished_lease_stay_blocked_after_reopen(tmp_path):
    ledger, store, op = setup_store(tmp_path)
    lease = store.claim(op, "fingerprint")
    for finish in (False, True):
        if finish:
            store.fail(lease)
        with pytest.raises(PaidBudgetError, match="derive opportunity"):
            SqliteDeriveOperationStore(ledger).claim(op, "fingerprint")


def test_completed_result_is_idempotent_and_binding_is_immutable(tmp_path):
    ledger, store, op = setup_store(tmp_path)
    lease = store.claim(op, "fingerprint")
    store.succeed(lease, b"sealed-result")
    replay = SqliteDeriveOperationStore(ledger).claim(op, "fingerprint")
    assert replay.result == b"sealed-result" and replay.token == lease.token
    with pytest.raises(PaidBudgetError):
        store.claim(op, "changed-input")
    with pytest.raises(PaidBudgetError):
        store.claim(
            replace(op, deadline_epoch_seconds=op.deadline_epoch_seconds + 1),
            "fingerprint",
        )


def test_only_actual_send_hook_consumes_three_shared_attempts(tmp_path):
    ledger, store, op = setup_store(tmp_path)
    lease = store.claim(op, "fingerprint")
    for _ in range(3):
        store.consume_attempt(lease)
    with pytest.raises(PaidBudgetError) as caught:
        SqliteDeriveOperationStore(ledger).consume_attempt(lease)
    assert caught.value.code == "AGENT_OPERATION_ATTEMPTS_EXHAUSTED"
    with sqlite3.connect(ledger.path) as db:
        assert db.execute("SELECT attempts FROM execution_operations").fetchone() == (
            3,
        )
    assert ledger.active_budget_id() is None


def test_stopped_original_run_and_expired_deadline_never_reopen(tmp_path):
    ledger, store, op = setup_store(tmp_path)
    lease = store.claim(op, "fingerprint")
    ledger.stop_execution("t", "run", context_scope=op.scope.conversation)
    with pytest.raises(PaidBudgetError):
        store.check_live(lease)
    with pytest.raises(PaidBudgetError):
        store.claim(
            replace(op, deadline_epoch_seconds=int(time.time()) - 1), "fingerprint"
        )


def test_initialization_is_explicit_and_requires_existing_ledger(tmp_path):
    ledger = SqlitePaidBudgetLedger(tmp_path / "paid.sqlite")
    SqliteDeriveOperationStore(ledger)
    with sqlite3.connect(ledger.path) as db:
        assert (
            db.execute(
                "SELECT name FROM sqlite_master WHERE name='derive_operations'"
            ).fetchone()
            is None
        )
    assert ledger.active_budget_id() is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_id", "new-exec"),
        ("subtask_id", "new-job"),
        ("purpose", "different-purpose"),
    ],
)
def test_changed_execution_job_purpose_cannot_expand_task_opportunity(
    tmp_path, field, value
):
    _, store, op = setup_store(tmp_path)
    store.claim(op, "fingerprint")
    with pytest.raises(PaidBudgetError) as caught:
        store.claim(
            replace(op, scope=replace(op.scope, **{field: value})), "fingerprint"
        )
    assert caught.value.code == "DERIVE_BINDING_CONFLICT"
