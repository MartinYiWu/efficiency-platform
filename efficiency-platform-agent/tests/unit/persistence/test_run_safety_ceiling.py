"""单任务安全上限不能被更宽的授权或重新打开账本突破。"""

from dataclasses import replace

import pytest
from test_paid_budget_ledger import lim, plan

from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger


def test_sixty_attempts_are_persistent_even_with_larger_authorization(tmp_path):
    path = tmp_path / "fake.db"
    book = SqlitePaidBudgetLedger(path)
    book.authorize(
        replace(
            plan(),
            max_calls=100,
            max_run_calls=100,
            max_cost_microunits=1000,
            max_run_cost_microunits=1000,
        ),
        lim(),
    )
    for _ in range(60):
        reservation = book.reserve(
            None, "same", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0
        )
        book.finish(reservation.reservation_id)
    with pytest.raises(PaidBudgetError, match="scope exhausted"):
        SqlitePaidBudgetLedger(path).reserve(
            None, "same", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0
        )
    assert book.snapshot()["calls"] == 60


def test_hundred_yuan_per_task_does_not_change_total_authorization(tmp_path):
    book = SqlitePaidBudgetLedger(tmp_path / "fake.db")
    book.authorize(
        replace(
            plan(),
            max_calls=10,
            max_run_calls=10,
            max_cost_microunits=300_000_000,
            max_run_cost_microunits=300_000_000,
        ),
        (replace(lim()[0], max_cost_microunits_per_attempt=60_000_000),),
    )
    reservation = book.reserve(
        None, "same", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0
    )
    book.finish(reservation.reservation_id)
    with pytest.raises(PaidBudgetError, match="scope exhausted"):
        book.reserve(None, "same", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0)
    assert book.snapshot()["cost_microunits"] == 60_000_000


def test_task_deadline_is_at_most_ten_minutes(tmp_path, monkeypatch):
    import efficiency_platform_agent.persistence.paid_budget as module

    monkeypatch.setattr(module.time, "time", lambda: 1000)
    book = SqlitePaidBudgetLedger(tmp_path / "fake.db")
    book.authorize(plan(), lim())
    reservation = book.reserve(
        None, "same", "p", "m", 1, 1, input_tokens=1, reasoning_tokens=0
    )
    assert reservation.deadline_epoch_ms == 1_600_000
