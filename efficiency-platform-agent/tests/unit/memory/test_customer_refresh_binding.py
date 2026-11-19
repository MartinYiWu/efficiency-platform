"""客服原运行等待中的绑定更新，不能新建任务或改变原请求身份。"""

import asyncio
import hashlib
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import BaseModel

from efficiency_platform_agent.agents.customer_service.model_gateway import (
    ReleaseStructuredModelGateway,
)
from efficiency_platform_agent.agents.customer_service.service import (
    CustomerServiceRunService,
)
from efficiency_platform_agent.agents.customer_service.state import (
    CustomerServiceRunRequest,
)
from efficiency_platform_agent.core.execution_control import (
    RunControl,
    consume_http_attempt,
    execution_scope,
)
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionGrant,
    MemoryExecutionRecord,
)
from efficiency_platform_agent.core.run_context_binding import (
    bind_conversation_scope,
    bind_run_context,
    current_run_context,
)
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)
from tests.integration.context_control.test_memory_execution_mysql import context
from tests.unit.agents.customer_service.test_evidence_pack import bundle


@pytest.mark.parametrize(
    "stream,derived", [(False, False), (True, False), (False, True), (True, True)]
)
async def test_original_live_frame_updates_binding_idempotently_without_new_task(
    stream, derived
):
    entered = asyncio.Event()
    proceed = asyncio.Event()
    checked = asyncio.Event()
    observed = []
    gateway_ref = []

    class Output(BaseModel):
        answer: str

    class Provider:
        async def complete(self, request):
            consume_http_attempt()
            observed.append(current_run_context())
            return SimpleNamespace(
                error=None, message=SimpleNamespace(content='{"answer":"synthetic"}')
            )

        async def stream(self, request):
            consume_http_attempt()
            observed.append(current_run_context())
            yield SimpleNamespace(
                error=None, delta='{"answer":"synthetic"}', finish_reason="stop"
            )

    class Graph:
        async def run(self, request, config, gateway):
            gateway_ref.append(gateway)
            await gateway.complete("sufficiency", {"call": 1}, Output)
            entered.set()
            await proceed.wait()
            selected = (
                gateway.with_model_policy(config.large_context_model_policy)
                if derived
                else gateway
            )
            if stream:
                await selected.stream_complete(
                    "evidence_extract", {"call": 2}, Output, lambda _: None
                )
            else:
                await selected.complete("evidence_extract", {"call": 2}, Output)
            gateway_ref.append(selected)
            assert current_run_context().memory_context.packet.packet_revision == 1
            checked.set()
            await asyncio.Event().wait()

    class Releases:
        async def get(self, *args):
            return bundle(large=9000)

    class Store:
        record = None

        async def get(self, *args):
            return self.record

        async def claim(self, memory, runtime, kind, fingerprint, deadline):
            self.record = MemoryExecutionRecord(
                memory,
                runtime,
                kind,
                fingerprint,
                min(deadline, memory.deadline_epoch_seconds),
                "ACTIVE",
                1,
                memory.packet.grant_epoch,
                memory.packet.source_epoch,
                memory.packet.deletion_epoch,
            )
            return self.record, True

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
            MemoryExecutionGrant("answer", "customer-service", "assistant_response"),
        ),
        packet_digest=memory_packet_digest(packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(packet),
    )
    store = Store()
    service = CustomerServiceRunService(
        Graph(),
        Releases(),
        lambda config: ReleaseStructuredModelGateway(Provider(), config),
        memory_execution_store=store,
    )
    request = CustomerServiceRunRequest(
        contract_version="customer-service-run/1",
        request_id="refresh-original",
        conversation_id=conversation,
        tenant_id=scope.tenant_id,
        user_id=scope.user_id,
        agent_release_id=uuid4(),
        message="synthetic frozen question",
        history=(),
    )
    with bind_conversation_scope(scope, memory_context=memory):
        view = await service.submit(request)
    await entered.wait()
    run = service._runs[view.run_id]
    original_task, original_control = run.task, run.control
    updated_packet = replace(
        packet,
        packet_revision=2,
        issued_at=packet.issued_at + 1,
        expires_at=min(packet.expires_at + 1, memory.deadline_epoch_seconds),
    )
    updated = replace(
        memory,
        packet=updated_packet,
        packet_digest=memory_packet_digest(updated_packet),
    )
    try:
        assert (
            await service.notify_context_wait(
                record=store.record, wait_event_id="wait-ref"
            )
            is True
        )
        event = run.events[-1]
        assert (
            event.event_type == "context_refresh_required"
            and event.payload.context_wait_ref == "wait-ref"
        )
        assert await service.refresh_memory_binding(store.record, updated) is True
        assert await service.refresh_memory_binding(store.record, updated) is True
        assert run.context_binding.memory_context == updated
        proceed.set()
        await asyncio.wait_for(checked.wait(), timeout=2)
        assert [item.memory_context.packet.packet_revision for item in observed] == [
            1,
            2,
        ]
        assert original_control.calls == 2
        with bind_run_context(observed[0]), execution_scope(original_control):
            if stream:
                await gateway_ref[1].stream_complete(
                    "evidence_extract", {"call": 2}, Output, lambda _: None
                )
            else:
                await gateway_ref[1].complete("evidence_extract", {"call": 2}, Output)
        assert original_control.calls == 2 and len(observed) == 2
        assert all(
            item.task_id == memory.packet.task_id
            and item.execution_id == memory.packet.execution_id
            for item in observed
        )
        for invalid_binding, invalid_control in (
            (None, original_control),
            (
                replace(
                    run.context_binding,
                    conversation=replace(scope, user_id="other"),
                    memory_context=None,
                ),
                original_control,
            ),
            (run.context_binding, RunControl()),
        ):
            with (
                bind_run_context(invalid_binding),
                execution_scope(invalid_control),
                pytest.raises(PermissionError),
            ):
                await gateway_ref[0].complete("sufficiency", {"invalid": True}, Output)
        assert original_control.calls == 2
        assert (
            run.task is original_task
            and not original_task.done()
            and run.control is original_control
        )
        assert (
            hashlib.sha256(run.request.model_dump_json().encode()).hexdigest()
            == store.record.request_fingerprint
        )
        assert (
            run.request == request
            and run.context_binding.deadline_epoch_seconds
            == store.record.deadline_epoch_seconds
        )
        changed = replace(updated, request_digest="f" * 64)
        assert await service.refresh_memory_binding(store.record, changed) is False
        assert (
            await service.refresh_memory_binding(
                replace(store.record, runtime_id=str(uuid4())), updated
            )
            is False
        )
        await service.stop_memory_execution(view.run_id)
        assert await service.refresh_memory_binding(store.record, updated) is False
        with (
            bind_run_context(run.context_binding),
            execution_scope(original_control),
            pytest.raises(PermissionError),
        ):
            await gateway_ref[0].complete("sufficiency", {"stopped": True}, Output)
        assert original_control.calls == 2
    finally:
        await service.close()
