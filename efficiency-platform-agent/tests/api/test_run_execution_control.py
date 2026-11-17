"""运行终止不能被迟到结果覆盖，后台共享操作必须随任务结束。"""

import asyncio

from test_customer_service_routes import CONVERSATION_ID, RELEASE_ID, Graph, Releases

from efficiency_platform_agent.agents.customer_service.service import (
    CustomerServiceRunService,
)
from efficiency_platform_agent.agents.customer_service.state import (
    CustomerServiceRunRequest,
    RunStatus,
)
from efficiency_platform_agent.core.execution_control import (
    RunControl,
    current_run_control,
)


def request():
    return CustomerServiceRunRequest(
        contract_version="customer-service-run/1",
        request_id="loop-test",
        conversation_id=CONVERSATION_ID,
        tenant_id="fake",
        user_id="fake",
        agent_release_id=RELEASE_ID,
        message="合成问题",
        history=(),
    )


async def test_cancel_cannot_be_overwritten_when_graph_suppresses_cancellation():
    entered = asyncio.Event()

    class SlowGraph(Graph):
        async def run(self, *args):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return await super().run(*args)

    service = CustomerServiceRunService(SlowGraph(), Releases(), lambda _: object())
    view = await service.submit(request())
    await entered.wait()
    await service.cancel(view.run_id)
    await service._runs[view.run_id].task
    run = service._runs[view.run_id]
    assert run.view.status is RunStatus.CANCELLED
    assert run.events[-1].event_type == "run.cancelled"
    assert not any(event.event_type == "answer.completed" for event in run.events)


async def test_timeout_closes_run_and_shared_pending_operations(monkeypatch):
    import efficiency_platform_agent.agents.customer_service.service as module

    monkeypatch.setattr(
        module, "RunControl", lambda: RunControl(timeout_ms=25), raising=False
    )
    controls = []

    class SlowGraph:
        async def run(self, *args):
            control = current_run_control()
            controls.append(control)
            assert control is not None

            async def work():
                await asyncio.Event().wait()

            await control.execute("same", work)

    service = CustomerServiceRunService(SlowGraph(), Releases(), lambda _: object())
    view = await service.submit(request())
    await asyncio.wait_for(service._runs[view.run_id].task, 1)
    run = service._runs[view.run_id]
    assert run.view.status is RunStatus.TIMED_OUT
    assert run.events[-1].payload.error_code == "AGENT_TASK_DEADLINE"
    assert controls[0].stopped is not None
    assert not controls[0].pending


async def test_debug_uses_own_control_and_closes_it():
    from types import SimpleNamespace

    from efficiency_platform_agent.agents.customer_service.state import (
        DebugKnowledgeBinding,
        DebugRequest,
    )

    controls = []

    class DebugGraph(Graph):
        async def run(self, *args):
            controls.append(current_run_control())
            return await super().run(*args)

    class DebugBundle(SimpleNamespace):
        def model_copy(self, *, update):
            return DebugBundle(**(vars(self) | update))

    class DebugReleases:
        async def get(self, release_id):
            return DebugBundle(knowledge_bindings=())

    service = CustomerServiceRunService(
        DebugGraph(), DebugReleases(), lambda _: object()
    )
    await service.debug(
        DebugRequest(
            contract_version="customer-service-rag-debug/1",
            agent_key="customer-service",
            tenant_id="fake",
            agent_release_id=RELEASE_ID,
            agent_version_id=RELEASE_ID,
            rag_policy_version_id=RELEASE_ID,
            question="合成问题",
            knowledge_bindings=(
                DebugKnowledgeBinding(
                    knowledge_base_id=RELEASE_ID, index_release_id=RELEASE_ID
                ),
            ),
        )
    )
    assert controls[0] is not None and controls[0].stopped is not None
