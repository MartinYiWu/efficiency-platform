"""客服清理必须来自原进程停止证明，并清除服务拥有的请求和派生缓冲。"""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest

from efficiency_platform_agent.agents.customer_service.graph import GraphResult
from efficiency_platform_agent.agents.customer_service.renderer import render_answer
from efficiency_platform_agent.agents.customer_service.retrieval_snapshot_repository import (
    InMemoryRetrievalSnapshotRepository,
)
from efficiency_platform_agent.agents.customer_service.service import (
    CustomerServiceNotFoundError,
    CustomerServiceRunService,
    CustomerServiceScopeError,
)
from efficiency_platform_agent.agents.customer_service.state import (
    AnswerMode,
    CustomerServiceAnswer,
    CustomerServiceRunRequest,
    GeneralAdvice,
    HistoryMessage,
)
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionGrant,
    MemoryExecutionRecord,
)
from efficiency_platform_agent.core.run_context_binding import bind_conversation_scope
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)
from tests.integration.context_control.test_memory_execution_mysql import context

MARKER = "SYNTHETIC_CSR_FORGOTTEN_BODY"


class Releases:
    async def get(self, release_id):
        return object()


class Store:
    record = None

    async def get(self, tenant, execution):
        return self.record

    async def claim(self, memory, runtime, kind, fingerprint, deadline):
        self.record = MemoryExecutionRecord(
            memory,
            runtime,
            kind,
            fingerprint,
            min(deadline, memory.deadline_epoch_seconds),
            "ACTIVE",
            memory.packet.execution_revision,
            0,
            0,
            0,
        )
        return self.record, True


class Graph:
    async def run(self, request, bundle, gateway):
        return GraphResult(
            rendered=render_answer(
                CustomerServiceAnswer(
                    contract_version="customer-service-answer/1",
                    answer_mode=AnswerMode.GENERAL_ADVICE,
                    general_advice=GeneralAdvice(paragraphs=(MARKER,)),
                ),
                (),
            ),
            stage_summaries=(("intent", MARKER),),
        )


async def setup_run():
    memory = context()
    conversation = uuid4()
    scope = replace(
        memory.packet.scope,
        domain="customer-service",
        top_level_agent_id="customer-service",
        session_id=str(conversation),
    )
    packet = replace(memory.packet, scope=scope)
    memory = replace(
        memory,
        packet=packet,
        policy=replace(
            memory.policy,
            domain="customer-service",
            agent_ids=frozenset({"customer-service"}),
        ),
        execution_grants=(
            MemoryExecutionGrant(
                "customer-service:answer_general",
                "customer-service",
                "assistant_response",
            ),
        ),
        packet_digest=memory_packet_digest(packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(packet),
    )
    store = Store()
    repository = InMemoryRetrievalSnapshotRepository()
    service = CustomerServiceRunService(
        Graph(),
        Releases(),
        lambda _: object(),
        repository,
        memory_execution_store=store,
    )
    request = CustomerServiceRunRequest(
        contract_version="customer-service-run/1",
        request_id="scrub-request",
        conversation_id=conversation,
        tenant_id=scope.tenant_id,
        user_id=scope.user_id,
        agent_release_id=uuid4(),
        message=MARKER,
        history=(HistoryMessage(role="assistant", content=MARKER),),
    )
    with bind_conversation_scope(scope, memory_context=memory):
        view = await service.submit(request)
    run = service._runs[view.run_id]
    await run.task
    assert MARKER in repr(run)
    return (
        service,
        store,
        repository,
        run,
        replace(store.record, state="REVOKED"),
        request,
    )


async def test_actual_join_precedes_scrub_and_replay_does_not_restore_request():
    service, store, repository, run, record, request = await setup_run()
    assert await service.scrub_memory_execution(record) is False
    await service.stop_memory_execution(run.view.run_id)
    repository.values[run.view.run_id] = object()
    assert await service.scrub_memory_execution(record) is True
    assert MARKER not in repr(run)
    assert not run.events and not run.streamed_blocks and run.context_binding is None
    assert run.view.run_id not in repository.values
    assert await service.scrub_memory_execution(record) is True
    with pytest.raises(CustomerServiceNotFoundError):
        await anext(service.events(run.view.run_id))
    store.record = record
    with (
        bind_conversation_scope(
            record.context.packet.scope, memory_context=record.context
        ),
        pytest.raises(CustomerServiceScopeError),
    ):
        await service.submit(request)


async def test_foreign_runtime_wrong_tenant_and_missing_snapshot_eraser_do_not_ack():
    service, _store, _repository, run, record, _ = await setup_run()
    await service.stop_memory_execution(run.view.run_id)
    foreign = CustomerServiceRunService(Graph(), Releases(), lambda _: object())
    assert await foreign.scrub_memory_execution(record) is False
    wrong_scope = replace(record.context.packet.scope, tenant_id="other")
    wrong_packet = replace(record.context.packet, scope=wrong_scope)
    wrong_context = replace(
        record.context,
        packet=wrong_packet,
        packet_digest=memory_packet_digest(wrong_packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(wrong_packet),
    )
    assert (
        await service.scrub_memory_execution(replace(record, context=wrong_context))
        is False
    )
    service.retrieval_snapshots = object()
    assert await service.scrub_memory_execution(record) is False
    assert MARKER in repr(run)


async def test_already_open_reader_cannot_yield_buffered_body_after_scrub():
    service, _, _, run, record, _ = await setup_run()
    iterator = service.events(run.view.run_id)
    await anext(iterator)
    await service.stop_memory_execution(run.view.run_id)
    assert await service.scrub_memory_execution(record) is True
    with pytest.raises(StopAsyncIteration):
        await anext(iterator)
    await iterator.aclose()


async def test_service_close_joins_actual_owned_tasks_before_dependencies_close():
    entered = asyncio.Event()

    class WaitingGraph:
        async def run(self, *args):
            entered.set()
            await asyncio.Event().wait()

    service = CustomerServiceRunService(WaitingGraph(), Releases(), lambda _: object())
    request = CustomerServiceRunRequest(
        contract_version="customer-service-run/1",
        request_id="shutdown",
        conversation_id=uuid4(),
        tenant_id="t",
        user_id="u",
        agent_release_id=uuid4(),
        message="synthetic",
        history=(),
    )
    view = await service.submit(request)
    await entered.wait()
    task = service._runs[view.run_id].task
    try:
        await service.close()
        assert task.done()
        with pytest.raises(CustomerServiceScopeError):
            await service.submit(
                request.model_copy(update={"request_id": "new-after-close"})
            )
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
