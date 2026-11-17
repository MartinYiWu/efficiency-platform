"""整批预检使用服务器实际模型绑定，不创建收费run或发送Provider请求。"""

from types import SimpleNamespace

import pytest

from efficiency_platform_agent.agents.hr.service import HrSkillService
from efficiency_platform_agent.api.hr_skill_routes import HrSkillEndpoint
from efficiency_platform_agent.contracts.hr import HrSkillRequest, HrWorkload
from efficiency_platform_agent.core.paid_budget import (
    PaidBudgetError,
    PaidBudgetPlan,
    PaidPriceLimit,
)
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger


class Bindings:
    async def published_metadata(self, key):
        assert key == "hr.requirements.evaluate"
        return {"model_route": "logical"}


class Provider:
    def paid_identity(self, logical):
        assert logical == "logical"
        return "p", "m"


@pytest.mark.asyncio
async def test_preflight_binds_actual_server_price_identity_and_never_consumes(
    tmp_path,
):
    ledger = SqlitePaidBudgetLedger(tmp_path / "fake-only.db")
    endpoint = HrSkillEndpoint(
        HrSkillService(Bindings(), Provider()), SimpleNamespace(ledger=ledger)
    )
    request = HrSkillRequest(
        run_id="plan",
        operation_id="plan-op",
        workload=[HrWorkload(run_ref="hr-trial-fixed")],
    )
    with pytest.raises(PaidBudgetError) as error:
        await endpoint.execute("tenant", 6109, request)
    assert error.value.code == "NO_BUDGET"
    ledger.authorize(
        PaidBudgetPlan(
            "fixture",
            3,
            300000,
            9999999999999,
            3,
            300000,
            600000,
            1,
            1,
            300000,
            30000,
            0,
            300000,
            30000,
            0,
        ),
        (
            PaidPriceLimit(
                "p",
                "m",
                65536,
                4096,
                100000,
                "fake-only-verified",
                "v1",
                65536,
                1000000,
                1000000,
                1000000,
            ),
        ),
    )
    result = await endpoint.execute("tenant", 6109, request)
    assert result["data"]["maximum_calls"] == 3
    assert ledger.snapshot()["calls"] == 0
    with ledger._db() as db:
        assert db.execute("SELECT COUNT(*) FROM execution_runs").fetchone()[0] == 0
