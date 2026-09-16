"""异步 Run 与实时 SSE 的离线集成测试。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest

from efficiency_platform_agent.api.app import create_app
from efficiency_platform_agent.api.sse import render_sse, stream_run_events
from efficiency_platform_agent.contracts.intent import IntentEnvelopeV1
from efficiency_platform_agent.contracts.requests import (
    CancelRunRequestV1,
    CreateRunRequestV1,
)
from efficiency_platform_agent.contracts.stream_events import RunStreamEventV1
from efficiency_platform_agent.core.budget import BudgetCharge, BudgetGuard
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    ProviderError,
    ProviderMessage,
    ProviderResult,
    ProviderStreamChunk,
    ProviderUsage,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.harness.local_real_factory import (
    build_local_agent_application,
)
from efficiency_platform_agent.harness.service import (
    AgentRuntimeService,
    RunPipelinePreparation,
)
from efficiency_platform_agent.orchestration.cancellation import (
    InMemoryCancellationSignal,
)
from efficiency_platform_agent.orchestration.contracts import (
    CheckpointView,
    GraphExecutionResult,
)
from efficiency_platform_agent.persistence.in_memory import (
    FixedClock,
    InMemoryRunEventStore,
    InMemoryRunRepository,
    SequenceIdGenerator,
)
from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
from efficiency_platform_agent.routing.strategy_router import StrategyRouter
from efficiency_platform_agent.runtime.event_hub import EventHub
from tests.unit.harness.test_local_real_factory import synthetic_settings


def direct_intent_result() -> ProviderResult:
    """使用合法完整契约驱动真实意图解释器进入普通对话。"""
    intent = IntentEnvelopeV1(
        domain="content",
        goal="解释品牌定位",
        task_type="general_chat",
        channels=[],
        needs_multi_agent=False,
        missing_fields=[],
        needs_clarification=False,
        confidence=0.99,
    )
    return ProviderResult(
        "intent/1",
        ProviderMessage("assistant", intent.model_dump_json()),
        ProviderUsage(3, 2, 0, 0, 1),
    )


def stream_envelopes(response: httpx.Response) -> list[RunStreamEventV1]:
    """从真实 HTTP SSE 响应解析并验证版本化事件信封。"""
    assert response.status_code == 200
    return [
        RunStreamEventV1.model_validate_json(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("local", [True, False], ids=["local", "model"])
async def test_conversation_direct_sse_orders_chat_and_closes_at_terminal(
    local,
) -> None:
    """本地与模型对话共用正式协议，正文完整且不产生交付物卡片数据。"""
    answer = "品牌定位是明确品牌为谁提供什么独特价值。"
    provider = FakeModelProvider(
        "synthetic",
        []
        if local
        else [
            direct_intent_result(),
            ProviderResult(
                "general-conversation/1",
                ProviderMessage("assistant", answer),
                ProviderUsage(5, 4, 0, 0, 2),
            ),
        ],
    )
    bundle = build_local_agent_application(
        synthetic_settings(), provider=provider, test_mode=True
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=bundle.app), base_url="http://test"
        ) as client:
            submitted = await client.post(
                "/v1/conversations/direct-protocol/messages",
                headers={"X-Tenant-ID": "tenant-1"},
                json={
                    "message": "你是谁" if local else "解释品牌定位",
                    "request_id": "direct-protocol",
                    "user_id": "user-1",
                },
            )
            assert submitted.status_code == 201
            run_id = submitted.json()["run_id"]
            await bundle.runtime.wait_for_background_tasks()
            run = await bundle.runtime.get_run(run_id, "tenant-1")
            assert run.status is RunStatus.SUCCEEDED
            assert run.strategy is StrategyMode.DIRECT
            assert set(run.output) == {"content"}
            stream = await asyncio.wait_for(
                client.get(
                    f"/v1/runs/{run_id}/events",
                    headers={"X-Tenant-ID": "tenant-1"},
                ),
                timeout=2,
            )
            events = stream_envelopes(stream)
            names = [event.event for event in events]
            assert names.count("assistant_started") == names.count("stream_done") == 1
            assert names.index("run_started") < names.index("assistant_started")
            assert names.index("assistant_started") < names.index("assistant_delta")
            assert names.index("assistant_delta") < names.index("stream_done")
            internal = await bundle.runtime.list_events(run_id, "tenant-1")
            internal_names = [event.event_type for event in internal]
            assert internal_names.index("run_started") < internal_names.index(
                "run_succeeded"
            )
            assert names[-1] == "stream_done"
            assert events[-1].payload == {"status": "succeeded", "degraded": False}
            assert [event.sequence for event in events] == list(
                range(1, len(events) + 1)
            )
            assert all(event.run_id == run_id for event in events)
            assert {"deliverable", "clarification_required", "stream_error"}.isdisjoint(
                names
            )
            deltas = [
                event.payload["delta"]
                for event in events
                if event.event == "assistant_delta"
            ]
            assert "".join(deltas) == run.output["content"]
            if local:
                assert "AI 内容运营助手" in run.output["content"]
            else:
                assert run.output["content"] == answer
            finished = await asyncio.wait_for(
                client.get(
                    f"/v1/runs/{run_id}/events",
                    headers={
                        "X-Tenant-ID": "tenant-1",
                        "Last-Event-ID": str(events[-1].sequence),
                    },
                ),
                timeout=2,
            )
            assert finished.status_code == 200
            assert finished.text == ""
    finally:
        await bundle.close()


@pytest.mark.asyncio
async def test_real_direct_stream_reaches_sse_while_run_is_running() -> None:
    """本地真实组合根必须在模型结束前发布 DIRECT 正文，而非终态伪分片。"""
    first_delta = asyncio.Event()
    release = asyncio.Event()

    class BlockingStreamingProvider(FakeModelProvider):
        """以固定脚本提供意图结果，并在普通对话中暂停流式正文。"""

        async def stream(self, request):
            """先发送首个正文片段，再等待测试确认其已被 SSE 接收。"""
            assert request.contract_version == "general-conversation/1"
            yield ProviderStreamChunk("品牌定位", ProviderUsage(5, 2, 0, 0, 2))
            first_delta.set()
            await release.wait()
            yield ProviderStreamChunk("需要明确价值。", ProviderUsage(5, 4, 0, 0, 3), "stop")

    provider = BlockingStreamingProvider("synthetic", [direct_intent_result()])
    bundle = build_local_agent_application(
        synthetic_settings(), provider=provider, test_mode=True
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=bundle.app), base_url="http://test"
        ) as client:
            submitted = await client.post(
                "/v1/conversations/realtime-direct/messages",
                headers={"X-Tenant-ID": "tenant-1"},
                json={
                    "message": "解释品牌定位",
                    "request_id": "realtime-direct",
                    "user_id": "user-1",
                },
            )
            assert submitted.status_code == 201
            run_id = submitted.json()["run_id"]
            await asyncio.wait_for(first_delta.wait(), timeout=2)

            running = await bundle.runtime.get_run(run_id, "tenant-1")
            replay_before_terminal = await bundle.event_hub.replay(run_id, 0)

            assert running.status is RunStatus.RUNNING
            assert [item.event for item in replay_before_terminal[-2:]] == [
                "assistant_started",
                "assistant_delta",
            ]
            assert replay_before_terminal[-1].payload == {"delta": "品牌定位"}

            release.set()
            await bundle.runtime.wait_for_background_tasks()
            completed = await bundle.runtime.get_run(run_id, "tenant-1")
            replay = await bundle.event_hub.replay(run_id, 0)
            deltas = [
                item.payload["delta"]
                for item in replay
                if item.event == "assistant_delta"
            ]

            assert completed.status is RunStatus.SUCCEEDED
            assert "".join(deltas) == completed.output["content"]
            assert deltas == ["品牌定位", "需要明确价值。"]
            assert [item.event for item in replay].count("assistant_started") == 1
    finally:
        release.set()
        await bundle.runtime.wait_for_background_tasks()
        await bundle.close()


@pytest.mark.asyncio
async def test_realtime_direct_does_not_retry_after_first_visible_provider_delta() -> None:
    """首片后发生可重试错误时，不得调用备用候选或拼接另一份回答。"""

    class PostDeltaFailureProvider(FakeModelProvider):
        """首个模型流交付正文后失败，后续调用代表不应触发的备用候选。"""

        def __init__(self) -> None:
            super().__init__("synthetic", [direct_intent_result()])
            self.stream_calls = 0

        async def stream(self, request):
            """仅第一候选交付首片并返回可重试错误。"""
            assert request.contract_version == "general-conversation/1"
            self.stream_calls += 1
            if self.stream_calls > 1:
                yield ProviderStreamChunk("不得拼接的备用回答")
                return
            yield ProviderStreamChunk("首片正文", ProviderUsage(5, 2, 0, 0, 2))
            yield ProviderStreamChunk(
                error=ProviderError("DOWN", "server_error", True, "temporary"),
                usage=ProviderUsage(5, 2, 0, 0, 2),
            )

    provider = PostDeltaFailureProvider()
    bundle = build_local_agent_application(
        synthetic_settings(), provider=provider, test_mode=True
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=bundle.app), base_url="http://test"
        ) as client:
            submitted = await client.post(
                "/v1/conversations/post-delta-failure/messages",
                headers={"X-Tenant-ID": "tenant-1"},
                json={
                    "message": "解释品牌定位",
                    "request_id": "post-delta-failure",
                    "user_id": "user-1",
                },
            )
            assert submitted.status_code == 201
            run_id = submitted.json()["run_id"]
            await bundle.runtime.wait_for_background_tasks()
            result = await bundle.runtime.get_run(run_id, "tenant-1")
            replay = await bundle.event_hub.replay(run_id, 0)
            deltas = [
                item.payload["delta"]
                for item in replay
                if item.event == "assistant_delta"
            ]

            assert result.status is RunStatus.FAILED
            assert result.output is None
            assert provider.stream_calls == 1
            assert deltas == ["首片正文"]
            assert "不得拼接的备用回答" not in "".join(deltas)
    finally:
        await bundle.runtime.wait_for_background_tasks()
        await bundle.close()


@pytest.mark.asyncio
async def test_conversation_direct_cancel_suppresses_late_model_sse() -> None:
    """在模型等待期间从 HTTP 取消，迟到回答不得变成增量或成功终态。"""
    started = asyncio.Event()
    release = asyncio.Event()

    class LateProvider(FakeModelProvider):
        """仅隔离外部模型等待，真实解释器、Graph、Harness 和 SSE 均运行。"""

        async def complete(self, request):
            if request.contract_version != "general-conversation/1":
                return await super().complete(request)
            started.set()
            await release.wait()
            return ProviderResult(
                "general-conversation/1",
                ProviderMessage("assistant", "不应显示的迟到正文"),
                ProviderUsage(5, 4, 0, 0, 2),
            )

    bundle = build_local_agent_application(
        synthetic_settings(),
        provider=LateProvider("synthetic", [direct_intent_result()]),
        test_mode=True,
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=bundle.app), base_url="http://test"
        ) as client:
            submitted = await client.post(
                "/v1/conversations/direct-cancel-protocol/messages",
                headers={"X-Tenant-ID": "tenant-1"},
                json={
                    "message": "解释品牌定位",
                    "request_id": "direct-cancel-protocol",
                    "user_id": "user-1",
                },
            )
            assert submitted.status_code == 201
            run_id = submitted.json()["run_id"]
            await asyncio.wait_for(started.wait(), timeout=2)
            accepted = await client.post(
                f"/v1/runs/{run_id}/cancel",
                headers={"X-Tenant-ID": "tenant-1"},
                json={"tenant_id": "tenant-1"},
            )
            assert accepted.status_code == 202
            release.set()
            await bundle.runtime.wait_for_background_tasks()
            stream = await asyncio.wait_for(
                client.get(
                    f"/v1/runs/{run_id}/events", headers={"X-Tenant-ID": "tenant-1"}
                ),
                timeout=2,
            )
            events = stream_envelopes(stream)
            names = [event.event for event in events]
            internal = await bundle.runtime.list_events(run_id, "tenant-1")
            internal_names = [event.event_type for event in internal]
            assert internal_names.index("run_cancel_requested") < internal_names.index(
                "run_cancelled"
            )
            assert "run_succeeded" not in internal_names
            assert names[-1] == "stream_done"
            assert names.count("stream_done") == 1
            assert events[-1].payload["status"] == "cancelled"
            assert {
                "assistant_started",
                "assistant_delta",
                "deliverable",
                "run_succeeded",
            }.isdisjoint(names)
            assert "不应显示的迟到正文" not in stream.text
            run = await bundle.runtime.get_run(run_id, "tenant-1")
            assert run.status is RunStatus.CANCELLED
            assert run.output is None
    finally:
        release.set()
        await bundle.runtime.wait_for_background_tasks()
        await bundle.close()


class BlockingGraph:
    """直到测试放行才返回的图，用于证明 POST 不等待执行完成。"""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def execute(self, selection, initial_state):
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return GraphExecutionResult(
            usage=UsageSnapshot(1, 1, 0, estimated=True),
            budget_state=BudgetGuard().start(
                ExecutionBudget(10, 2, 100, 100, 100, 100),
                now_epoch_ms=initial_state["budget_state"]["started_at_epoch_ms"],
            ),
            checkpoint=CheckpointView(
                initial_state["run_id"], f"s2:{selection.mode}:1", "cp-1"
            ),
            facts=(),
            next_status=RunStatus.SUCCEEDED,
            output=JsonObject((("content", "完成"),)),
        )


class RealtimeDirectGraph(BlockingGraph):
    """等待放行后返回已通过实时端口发送的 DIRECT 正文。"""

    async def execute(self, selection, initial_state):
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return GraphExecutionResult(
            usage=UsageSnapshot(1, 1, 0, estimated=True),
            budget_state=BudgetGuard().start(
                ExecutionBudget(10, 2, 100, 100, 100, 100),
                now_epoch_ms=initial_state["budget_state"]["started_at_epoch_ms"],
            ),
            checkpoint=CheckpointView(
                initial_state["run_id"], f"s2:{selection.mode}:1", "cp-realtime"
            ),
            facts=(),
            next_status=RunStatus.SUCCEEDED,
            output=JsonObject((("content", "实时正文"),)),
        )


class CancellationAwareGraph:
    """等待取消信号并返回取消状态的协作式图。"""

    def __init__(self, signal: InMemoryCancellationSignal) -> None:
        self.signal = signal
        self.started = asyncio.Event()

    async def execute(self, selection, initial_state):
        run_id = initial_state["run_id"]
        self.started.set()
        await self.signal.wait_requested(run_id)
        return GraphExecutionResult(
            usage=UsageSnapshot(),
            budget_state=BudgetGuard().start(
                ExecutionBudget(10, 2, 100, 100, 100, 100),
                now_epoch_ms=initial_state["budget_state"]["started_at_epoch_ms"],
            ),
            checkpoint=CheckpointView(run_id, f"s2:{selection.mode}:1", "cp-cancel"),
            facts=(),
            next_status=RunStatus.CANCELLED,
        )


def request(request_id: str = "request-1") -> CreateRunRequestV1:
    """构造 Direct Run 请求。"""
    return CreateRunRequestV1(
        request_id=request_id,
        tenant_id="tenant-1",
        user_id="user-1",
        input_text="生成运营文案",
        requested_strategy=StrategyMode.DIRECT,
    )


def service_with_graph(
    graph: object,
    *,
    signal: InMemoryCancellationSignal | None = None,
    event_hub: EventHub | None = None,
    output_streamer=None,
) -> AgentRuntimeService:
    """构造完全离线的真实 Harness 服务。"""
    return AgentRuntimeService(
        repository=InMemoryRunRepository(),
        event_store=InMemoryRunEventStore(),
        router=StrategyRouter(frozenset({StrategyMode.DIRECT})),
        graph_runtime=graph,
        budget_guard=BudgetGuard(),
        budget=ExecutionBudget(10, 2, 100, 100, 100, 100),
        clock=FixedClock(1),
        id_generator=SequenceIdGenerator(),
        cancellation_signal=signal,
        event_hub=event_hub,
        output_streamer=output_streamer,
    )


@pytest.mark.asyncio
async def test_running_direct_run_publishes_realtime_delta_without_terminal_duplicate() -> (
    None
):
    """Harness 仅在运行中接收实时正文，结算时不再发送同一 DIRECT 内容。"""
    graph = RealtimeDirectGraph()
    hub = EventHub()
    service = service_with_graph(graph, event_hub=hub)

    queued = await service.create_and_schedule(request("request-realtime-direct"))
    await asyncio.wait_for(graph.started.wait(), timeout=0.2)

    accepted = await service.publish_assistant_delta(queued.run_id, "实时正文")
    before_terminal = await hub.replay(queued.run_id, 0)

    assert accepted is True
    assert [item.event for item in before_terminal[-2:]] == [
        "assistant_started",
        "assistant_delta",
    ]
    assert before_terminal[-1].payload == {"delta": "实时正文"}
    assert (await service.get_run(queued.run_id, "tenant-1")).status is RunStatus.RUNNING

    graph.release.set()
    await service.wait_for_background_tasks()
    replay = await hub.replay(queued.run_id, 0)
    deltas = [
        item.payload["delta"] for item in replay if item.event == "assistant_delta"
    ]

    assert deltas == ["实时正文"]
    assert [item.event for item in replay].count("assistant_started") == 1
    assert replay[-1].payload == {"status": "succeeded", "degraded": False}


@pytest.mark.asyncio
async def test_partial_output_stream_failure_finishes_complete_but_degraded() -> None:
    """已经发送的增量失败后必须补齐安全正文，不能伪装为完整成功。"""

    async def broken_streamer(_run_id: str, _output: object) -> AsyncIterator[str]:
        yield "部分增量"
        raise RuntimeError("provider-private-error")

    graph = BlockingGraph()
    hub = EventHub()
    service = service_with_graph(graph, event_hub=hub, output_streamer=broken_streamer)
    queued = await service.create_and_schedule(request("request-partial-stream"))
    await graph.started.wait()
    graph.release.set()
    await service.wait_for_background_tasks()

    result = await service.get_run(queued.run_id, "tenant-1")
    replay = await hub.replay(queued.run_id, 0)
    deltas = [
        item.payload["delta"] for item in replay if item.event == "assistant_delta"
    ]

    assert result.status is RunStatus.SUCCEEDED
    assert result.degraded is True
    assert deltas == ["部分增量", "\n\n完成"]
    assert [item.event for item in replay[-3:]] == [
        "stream_error",
        "assistant_delta",
        "stream_done",
    ]
    assert replay[-3].payload == {
        "code": "OUTPUT_STREAM_INTERRUPTED",
        "category": "presentation",
        "retryable": False,
        "safe_message": "流式输出中断，已补充完整结果",
    }
    assert replay[-1].payload == {"status": "succeeded", "degraded": True}


@pytest.mark.asyncio
async def test_pipeline_failure_keeps_intent_usage_and_degraded_facts() -> None:
    class IntentFailure(RuntimeError):
        code = "INTENT_PROVIDER_ERROR"
        safe_message = "意图模型调用未完成"
        usage = UsageSnapshot(3, 2, 7, estimated=True)
        degraded = True
        attempts = (object(), object(), object())

    graph = BlockingGraph()
    hub = EventHub()
    runtime = service_with_graph(graph, event_hub=hub)

    async def prepare(_context):
        raise IntentFailure()

    queued = await runtime.create_and_schedule_pipeline(
        request("request-intent-failure"), prepare
    )
    await runtime.wait_for_background_tasks()
    result = await runtime.get_run(queued.run_id, "tenant-1")
    replay = await hub.replay(queued.run_id, 0)

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "INTENT_PROVIDER_ERROR"
    assert result.usage.input_tokens == 3
    assert result.usage.output_tokens == 2
    assert result.usage.cost_microunits == 7
    assert result.usage.estimated is True
    assert result.degraded is True
    record = await runtime.repository.get(queued.run_id, "tenant-1")
    assert record is not None
    assert record.budget_state.consumed.iterations == 3
    usage_event = next(item for item in replay if item.event == "usage_update")
    assert usage_event.payload["input_tokens"] == 3
    assert replay[-2].event == "stream_error"
    assert replay[-1].payload == {"status": "failed", "degraded": True}


@pytest.mark.asyncio
async def test_pipeline_budget_error_preserves_stable_timed_out_status() -> None:
    runtime = service_with_graph(BlockingGraph())

    async def prepare(context):
        assert context.remaining_budget.input_tokens == 100
        return RunPipelinePreparation(
            request("request-budget-failure"),
            usage=UsageSnapshot(101, 1, 0, estimated=True),
            charge=BudgetCharge(iterations=2, input_tokens=101, output_tokens=1),
        )

    queued = await runtime.create_and_schedule_pipeline(
        request("request-budget-failure"), prepare
    )
    await runtime.wait_for_background_tasks()
    result = await runtime.get_run(queued.run_id, "tenant-1")
    events = await runtime.list_events(queued.run_id, "tenant-1")

    assert result.status is RunStatus.TIMED_OUT
    assert result.error is not None
    assert result.error.code == "BUDGET_EXHAUSTED"
    assert result.usage.input_tokens == 101
    record = await runtime.repository.get(queued.run_id, "tenant-1")
    assert record is not None
    assert record.budget_state.consumed.input_tokens == 101
    assert record.budget_state.consumed.iterations == 2
    assert [event.event_type for event in events[-2:]] == [
        "budget_exhausted",
        "run_timed_out",
    ]


@pytest.mark.asyncio
async def test_pipeline_cancelled_in_queued_callback_never_calls_prepare() -> None:
    signal = InMemoryCancellationSignal()
    hub = EventHub()
    runtime = service_with_graph(BlockingGraph(), signal=signal, event_hub=hub)
    prepare_called = False

    async def prepare(_context):
        nonlocal prepare_called
        prepare_called = True
        return RunPipelinePreparation(request("request-cancel-before-intent"))

    async def cancel_before_schedule(view):
        await runtime.cancel_run(view.run_id, CancelRunRequestV1(tenant_id="tenant-1"))

    queued = await runtime.create_and_schedule_pipeline(
        request("request-cancel-before-intent"),
        prepare,
        on_queued=cancel_before_schedule,
    )
    await runtime.wait_for_background_tasks()
    result = await runtime.get_run(queued.run_id, "tenant-1")
    replay = await hub.replay(queued.run_id, 0)

    assert prepare_called is False
    assert result.status is RunStatus.CANCELLED
    assert not any(item.event == "intent_detected" for item in replay)
    assert replay[-1].payload == {"status": "cancelled", "degraded": False}


@pytest.mark.asyncio
async def test_pipeline_cancelled_while_prepare_is_running_reaches_terminal_state() -> (
    None
):
    signal = InMemoryCancellationSignal()
    hub = EventHub()
    runtime = service_with_graph(BlockingGraph(), signal=signal, event_hub=hub)
    prepare_started = asyncio.Event()
    release_prepare = asyncio.Event()

    async def prepare(_context):
        prepare_started.set()
        await release_prepare.wait()
        return RunPipelinePreparation(request("request-cancel-during-intent"))

    queued = await runtime.create_and_schedule_pipeline(
        request("request-cancel-during-intent"), prepare
    )
    await asyncio.wait_for(prepare_started.wait(), timeout=0.2)
    accepted = await runtime.cancel_run(
        queued.run_id, CancelRunRequestV1(tenant_id="tenant-1")
    )
    assert accepted.status is RunStatus.CANCELLED

    release_prepare.set()
    await runtime.wait_for_background_tasks()
    result = await runtime.get_run(queued.run_id, "tenant-1")
    replay = await hub.replay(queued.run_id, 0)

    assert result.status is RunStatus.CANCELLED
    assert replay[-1].event == "stream_done"
    assert replay[-1].payload == {"status": "cancelled", "degraded": False}


@pytest.mark.asyncio
async def test_cancel_wins_when_running_graph_returns_a_non_cancel_result() -> None:
    signal = InMemoryCancellationSignal()
    hub = EventHub()
    graph = BlockingGraph()
    runtime = service_with_graph(graph, signal=signal, event_hub=hub)

    queued = await runtime.create_and_schedule(request("request-cancel-race"))
    await asyncio.wait_for(graph.started.wait(), timeout=0.2)
    accepted = await runtime.cancel_run(
        queued.run_id, CancelRunRequestV1(tenant_id="tenant-1")
    )
    assert accepted.status is RunStatus.RUNNING

    graph.release.set()
    await runtime.wait_for_background_tasks()
    result = await runtime.get_run(queued.run_id, "tenant-1")
    replay = await hub.replay(queued.run_id, 0)

    assert result.status is RunStatus.CANCELLED
    assert replay[-1].event == "stream_done"
    assert replay[-1].payload == {"status": "cancelled", "degraded": False}


@pytest.mark.asyncio
async def test_post_create_returns_queued_before_graph_completes() -> None:
    graph = BlockingGraph()
    service = service_with_graph(graph)
    app = create_app(service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await asyncio.wait_for(
            client.post(
                "/v1/runs",
                json=request().model_dump(mode="json"),
                headers={"X-Tenant-ID": "tenant-1"},
            ),
            timeout=0.2,
        )
        assert response.status_code == 201
        assert response.json()["status"] == "queued"
        await asyncio.wait_for(graph.started.wait(), 0.2)
        graph.release.set()
        await service.wait_for_background_tasks()

    result = await service.get_run(response.json()["run_id"], "tenant-1")
    assert result.status is RunStatus.SUCCEEDED


def test_app_allows_only_declared_local_frontend_cors_origin() -> None:
    graph = BlockingGraph()
    app = create_app(service_with_graph(graph))

    async def preflight(origin: str) -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.options(
                "/v1/runs",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "X-Tenant-ID,Content-Type",
                },
            )

    allowed = asyncio.run(preflight("http://127.0.0.1:5190"))
    denied = asyncio.run(preflight("https://untrusted.example"))

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5190"
    assert "access-control-allow-origin" not in denied.headers


@pytest.mark.asyncio
async def test_concurrent_idempotent_schedule_returns_same_queued_run_once() -> None:
    graph = BlockingGraph()
    service = service_with_graph(graph)

    first, second = await asyncio.gather(
        service.create_and_schedule(request("request-idempotent")),
        service.create_and_schedule(request("request-idempotent")),
    )

    assert first.run_id == second.run_id
    assert first.status is second.status is RunStatus.QUEUED
    await asyncio.wait_for(graph.started.wait(), 0.2)
    assert graph.calls == 1
    graph.release.set()
    await service.wait_for_background_tasks()


@pytest.mark.asyncio
async def test_sse_replays_history_receives_live_event_and_skips_cursor() -> None:
    hub = EventHub()
    await hub.publish(RunStreamEventV1(event="run_started", run_id="run-1", sequence=1))
    iterator = stream_run_events(
        hub,
        "run-1",
        after_sequence=1,
        keep_alive_seconds=1,
    )

    pending = asyncio.create_task(anext(iterator))
    await asyncio.sleep(0)
    await hub.publish(
        RunStreamEventV1(
            event="assistant_delta",
            run_id="run-1",
            sequence=2,
            payload={"delta": "新片段"},
        )
    )

    chunk = await asyncio.wait_for(pending, 0.2)
    assert "id: 1" not in chunk
    assert "id: 2" in chunk
    assert json.loads(
        next(line[6:] for line in chunk.splitlines() if line.startswith("data: "))
    )["payload"] == {"delta": "新片段"}
    await iterator.aclose()


@pytest.mark.asyncio
async def test_sse_emits_keep_alive_while_idle() -> None:
    hub = EventHub()
    iterator = stream_run_events(
        hub,
        "run-idle",
        after_sequence=0,
        keep_alive_seconds=0.01,
    )

    assert await asyncio.wait_for(anext(iterator), 0.2) == ": keep-alive\n\n"
    await iterator.aclose()


@pytest.mark.asyncio
async def test_sse_route_replays_terminal_history_and_honors_last_event_id() -> None:
    graph = BlockingGraph()
    service = service_with_graph(graph)
    queued = await service.create_and_schedule(request("request-sse-route"))
    await asyncio.wait_for(graph.started.wait(), 0.2)
    graph.release.set()
    await service.wait_for_background_tasks()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)),
        base_url="http://test",
    ) as client:
        full = await client.get(
            f"/v1/runs/{queued.run_id}/events",
            headers={"X-Tenant-ID": "tenant-1"},
        )
        ids = [
            int(line[4:]) for line in full.text.splitlines() if line.startswith("id: ")
        ]
        resumed = await client.get(
            f"/v1/runs/{queued.run_id}/events",
            headers={
                "X-Tenant-ID": "tenant-1",
                "Last-Event-ID": str(ids[0]),
            },
        )
        finished = await client.get(
            f"/v1/runs/{queued.run_id}/events",
            headers={
                "X-Tenant-ID": "tenant-1",
                "Last-Event-ID": str(ids[-1]),
            },
        )

    assert full.status_code == resumed.status_code == finished.status_code == 200
    assert full.headers["content-type"].startswith("text/event-stream")
    assert full.headers["cache-control"] == "no-cache"
    assert "event: run_started" in full.text
    assert "event: stream_done" in full.text
    assert f"id: {ids[0]}" not in resumed.text
    assert f"id: {ids[-1]}" in resumed.text
    assert finished.text == ""


def test_render_sse_uses_contract_event_and_sequence() -> None:
    chunk = render_sse(
        RunStreamEventV1(
            event="assistant_delta",
            run_id="run-1",
            sequence=7,
            payload={"delta": "片段"},
        )
    )

    assert chunk.startswith("id: 7\nevent: assistant_delta\n")
    assert chunk.endswith("\n\n")


@pytest.mark.asyncio
async def test_cancel_running_background_run_reaches_cancelled_and_stream_done() -> (
    None
):
    signal = InMemoryCancellationSignal()
    hub = EventHub()
    graph = CancellationAwareGraph(signal)
    service = service_with_graph(graph, signal=signal, event_hub=hub)

    queued = await service.create_and_schedule(request("request-cancel"))
    await asyncio.wait_for(graph.started.wait(), 0.2)
    accepted = await service.cancel_run(
        queued.run_id,
        CancelRunRequestV1(tenant_id="tenant-1"),
    )
    await service.wait_for_background_tasks()

    final = await service.get_run(queued.run_id, "tenant-1")
    assert accepted.status is RunStatus.RUNNING
    assert final.status is RunStatus.CANCELLED
    replay = await hub.replay(queued.run_id, 0)
    assert replay[-1].event == "stream_done"
    assert replay[-1].payload["status"] == "cancelled"
