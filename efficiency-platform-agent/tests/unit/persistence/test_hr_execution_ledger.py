"""同一HR运行跨阶段/进程的停止与三次操作尝试不能重新领取额度。"""

import pytest

from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger


def test_run_deadline_and_attempts_survive_reopen(tmp_path):
    path = tmp_path / "fake.db"
    ledger = SqlitePaidBudgetLedger(path)
    first = ledger.bind_execution("tenant", "run", 600000)
    reopened = SqlitePaidBudgetLedger(path)
    assert reopened.bind_execution("tenant", "run", 600000) == first
    for _ in range(3):
        reopened.consume_execution_attempt("tenant", "run", "original-operation")
    with pytest.raises(PaidBudgetError) as caught:
        SqlitePaidBudgetLedger(path).consume_execution_attempt(
            "tenant", "run", "original-operation"
        )
    assert caught.value.code == "AGENT_OPERATION_ATTEMPTS_EXHAUSTED"
    with pytest.raises(PaidBudgetError):
        reopened.consume_execution_attempt("tenant", "run", "different-operation")


def test_cancel_is_persistent_and_tenant_does_not_alias_other_run(tmp_path):
    ledger = SqlitePaidBudgetLedger(tmp_path / "fake.db")
    ledger.bind_execution("tenant", "run", 600000)
    ledger.bind_execution("other", "run", 600000)
    ledger.stop_execution("tenant", "run")
    with pytest.raises(PaidBudgetError):
        ledger.check_execution("tenant", "run")
    ledger.check_execution("other", "run")


def test_duplicate_stage_result_is_immutable_and_scoped(tmp_path):
    ledger = SqlitePaidBudgetLedger(tmp_path / "fake.db")
    ledger.bind_execution("tenant", "run", 600000)
    assert ledger.claim_execution_operation("tenant", "run", "op", "input-hash")
    assert not ledger.claim_execution_operation("tenant", "run", "op", "input-hash")
    with pytest.raises(PaidBudgetError):
        ledger.claim_execution_operation("tenant", "run", "op", "changed-hash")


def test_execution_timeout_cannot_be_renewed(tmp_path, monkeypatch):
    import efficiency_platform_agent.persistence.paid_budget as module

    monkeypatch.setattr(module.time, "time", lambda: 1000)
    ledger = SqlitePaidBudgetLedger(tmp_path / "fake.db")
    assert ledger.bind_execution("tenant", "run", 1000) == 1_001_000
    monkeypatch.setattr(module.time, "time", lambda: 1002)
    with pytest.raises(PaidBudgetError):
        ledger.bind_execution("tenant", "run", 600000)
