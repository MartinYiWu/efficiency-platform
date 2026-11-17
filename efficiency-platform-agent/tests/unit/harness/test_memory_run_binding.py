"""受保护运行的完整幂等比较必须覆盖先读和真实创建竞争分支。"""

import asyncio

import pytest

from efficiency_platform_agent.contracts.requests import CreateRunRequestV1
from efficiency_platform_agent.core.budget import BudgetGuard
from efficiency_platform_agent.core.memory import ConversationScope
from efficiency_platform_agent.core.run import ExecutionBudget
from efficiency_platform_agent.core.run_context_binding import bind_conversation_scope
from efficiency_platform_agent.harness.errors import HarnessError
from efficiency_platform_agent.harness.service import AgentRuntimeService
from efficiency_platform_agent.persistence.in_memory import (
    FixedClock,
    InMemoryRunEventStore,
    InMemoryRunRepository,
    SequenceIdGenerator,
)


def service(repository=None):
    return AgentRuntimeService(
        repository=repository or InMemoryRunRepository(),
        event_store=InMemoryRunEventStore(),
        router=None,
        graph_runtime=None,
        budget_guard=BudgetGuard(),
        budget=ExecutionBudget(10, 2, 100, 100, 100000, 100),
        clock=FixedClock(100000),
        id_generator=SequenceIdGenerator(),
    )


def request(**changes):
    return CreateRunRequestV1(
        **(
            dict(request_id="r", tenant_id="t", user_id="u", input_text="original")
            | changes
        )
    )


SCOPE = ConversationScope("t", "u", "operations", "operations", "CONVERSATION", "s")


@pytest.mark.asyncio
async def test_public_replay_cannot_read_protected_run():
    runtime = service()
    with bind_conversation_scope(SCOPE):
        await runtime._create_queued(request())
    with pytest.raises(HarnessError) as failure:
        await runtime._create_queued(request())
    assert failure.value.code == "CONTEXT_SCOPE_MISMATCH"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"input_text": "changed"},
        {"workflow_id": "different"},
        {"strategy_payload": {"altered": True}},
        {"strategy_payload_schema_version": "different/1"},
    ],
)
async def test_same_scope_different_business_input_is_conflict(changes):
    runtime = service()
    with bind_conversation_scope(SCOPE):
        first, _ = await runtime._create_queued(request())
        replay, created = await runtime._create_queued(request())
        assert replay.run_id == first.run_id and not created
        with pytest.raises(HarnessError) as failure:
            await runtime._create_queued(request(**changes))
        assert failure.value.code == "CONTEXT_SCOPE_MISMATCH"


class RacingRepository(InMemoryRunRepository):
    def __init__(self):
        super().__init__()
        self.arrivals = 0
        self.gate = asyncio.Event()

    async def get_by_request_id(self, request_id, tenant_id):
        if self.arrivals < 2:
            self.arrivals += 1
            if self.arrivals == 2:
                self.gate.set()
            await self.gate.wait()
            return None
        return await super().get_by_request_id(request_id, tenant_id)


@pytest.mark.asyncio
async def test_two_missing_reads_cannot_bypass_full_fingerprint_after_create_race():
    repository = RacingRepository()
    runtime = service(repository)
    with bind_conversation_scope(SCOPE):
        results = await asyncio.gather(
            runtime._create_queued(request()),
            runtime._create_queued(request(input_text="other")),
            return_exceptions=True,
        )
    assert repository.arrivals == 2
    assert sum(isinstance(result, HarnessError) for result in results) == 1
    assert len(repository._runs) == 1
