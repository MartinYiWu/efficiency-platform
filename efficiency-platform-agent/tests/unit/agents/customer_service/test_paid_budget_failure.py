"""预算耗尽必须终止运行，不能包装成知识不足或可选校验失败。"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_evidence_assembly import group_fixture
from test_evidence_pack import bundle

from efficiency_platform_agent.agents.customer_service.conflict_screen import (
    screen_conflicts,
)
from efficiency_platform_agent.agents.customer_service.model_gateway import (
    ReleaseStructuredModelGateway,
)
from efficiency_platform_agent.agents.customer_service.state import SufficiencyDecision
from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.core.run import ProviderError


@pytest.mark.parametrize("batch", [False, True])
async def test_conflict_gate_does_not_swallow_or_retry_paid_budget_stop(batch):
    _, parents = group_fixture()
    parents = (parents[0], parents[1].model_copy(update={"document_id": uuid4()}))
    members = {
        (p.knowledge_base_id, p.document_id, p.document_version_id, p.index_release_id)
        for p in parents
    }
    calls = []

    class Gateway:
        async def complete(self, *args):
            calls.append(True)
            raise PaidBudgetError("BUDGET_EXHAUSTED", "预算已停止")

    with pytest.raises(PaidBudgetError):
        await screen_conflicts(
            parents,
            question="question",
            gateway=Gateway(),
            members=members,
            stage_bound=True,
            batch_enabled=batch,
        )
    assert len(calls) == 1


async def test_model_gateway_preserves_fatal_paid_budget_error_type():
    class Provider:
        async def complete(self, request):
            return SimpleNamespace(
                error=ProviderError("NO_BUDGET", "budget", False, "预算未授权"),
                message=None,
            )

    with pytest.raises(PaidBudgetError):
        await ReleaseStructuredModelGateway(Provider(), bundle()).complete(
            "sufficiency", {}, SufficiencyDecision
        )
