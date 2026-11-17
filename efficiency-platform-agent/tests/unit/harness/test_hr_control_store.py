"""HR服务器控制装配只使用临时Fake账本，不加载真实凭据。"""

import pytest

from efficiency_platform_agent.core.execution_control import consume_http_attempt
from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger


async def test_reopen_store_cannot_reset_operation_attempts(tmp_path):
    from efficiency_platform_agent.harness.hr_factory import PersistentHrRunControlStore

    path = tmp_path / "fake.db"
    store = PersistentHrRunControlStore(SqlitePaidBudgetLedger(path))
    control = await store.get("tenant", "run")

    async def request():
        for _ in range(3):
            consume_http_attempt()
        return "synthetic"

    assert await control.execute("original-op", request) == "synthetic"
    reopened = await PersistentHrRunControlStore(SqlitePaidBudgetLedger(path)).get(
        "tenant", "run"
    )
    with pytest.raises(PaidBudgetError):
        await reopened.execute("original-op", request)
    await store.cancel("tenant", "run")
    with pytest.raises(PaidBudgetError):
        await PersistentHrRunControlStore(SqlitePaidBudgetLedger(path)).get(
            "tenant", "run"
        )
