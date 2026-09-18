"""验证运营 Run 的阶段事件和用户级错误不会泄露内部细节。"""

from __future__ import annotations

import asyncio

import pytest

from efficiency_platform_agent.contracts.requests import CreateRunRequestV1
from efficiency_platform_agent.core.budget import BudgetGuard
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.harness.service import AgentRuntimeService
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
from efficiency_platform_agent.routing.strategy_router import StrategyRouter
from efficiency_platform_agent.runtime.event_hub import EventHub


class OperationSuccessGraph:
    """返回一个包含三平台成品的最小运营图替身。"""

    async def execute(self, _selection, state):
        budget = BudgetGuard().start(
            ExecutionBudget(20, 4, 100, 100, 100, 100),
            now_epoch_ms=state["budget_state"]["started_at_epoch_ms"],
        )
        output = JsonObject(
            (
                ("content", "已完成三平台内容"),
                (
                    "deliverable_set",
                    JsonObject(
                        (
                            (
                                "deliverables",
                                (
                                    JsonObject(
                                        (
                                            ("contract_version", "deliverable/1"),
                                            ("platform", "wechat"),
                                            ("title", "公众号标题"),
                                            ("body", "公众号成品"),
                                            ("hashtags", ()),
                                            ("format_notes", ()),
                                            ("citations", ()),
                                            ("warnings", ()),
                                        )
                                    ),
                                    JsonObject(
                                        (
                                            ("contract_version", "deliverable/1"),
                                            ("platform", "xiaohongshu"),
                                            ("title", "小红书标题"),
                                            ("body", "小红书成品"),
                                            ("hashtags", ()),
                                            ("format_notes", ()),
                                            ("citations", ()),
                                            ("warnings", ()),
                                        )
                                    ),
                                    JsonObject(
                                        (
                                            ("contract_version", "deliverable/1"),
                                            ("platform", "toutiao"),
                                            ("title", "头条标题"),
                                            ("body", "头条成品"),
                                            ("hashtags", ()),
                                            ("format_notes", ()),
                                            ("citations", ()),
                                            ("warnings", ()),
                                        )
                                    ),
                                ),
                            ),
                            ("summary", "已完成三平台内容"),
                            ("degraded", False),
                        )
                    ),
                ),
            )
        )
        return GraphExecutionResult(
            UsageSnapshot(3, 5, 0, estimated=True),
            budget,
            CheckpointView(state["run_id"], "s2:multi_agent:1", "cp-operation"),
            (),
            RunStatus.SUCCEEDED,
            output,
        )


class OperationFailureGraph:
    """抛出含内部信息的异常，验证最终事件只暴露固定错误。"""

    async def execute(self, _selection, _state):
        raise ValueError("rendered_prompt=secret prompt; provider raw response")


class OperationReportingGraph(OperationSuccessGraph):
    """通过真实窄端口报告阶段，并尝试用 payload 覆盖可信阶段。"""

    async def execute(self, selection, state):
        from efficiency_platform_agent.runtime.operation_progress import (
            report_operation_progress,
        )

        await report_operation_progress(
            "understanding_request",
            payload={"phase": "creating_content", "completed": 0, "target": 1},
        )
        return await super().execute(selection, state)


class ConcurrentReportingGraph(OperationSuccessGraph):
    """并发 Run 中重复报告同一真实阶段。"""

    async def execute(self, selection, state):
        from efficiency_platform_agent.runtime.operation_progress import (
            report_operation_progress,
        )

        await report_operation_progress("understanding_request")
        await asyncio.sleep(0)
        await report_operation_progress("understanding_request")
        return await super().execute(selection, state)


def operation_request(request_id: str, graph: object) -> AgentRuntimeService:
    """构造运营多 Agent Harness。"""
    return AgentRuntimeService(
        repository=InMemoryRunRepository(),
        event_store=InMemoryRunEventStore(),
        router=StrategyRouter(frozenset({StrategyMode.MULTI_AGENT})),
        graph_runtime=graph,
        budget_guard=BudgetGuard(),
        budget=ExecutionBudget(20, 4, 100, 100, 100, 100),
        clock=FixedClock(1),
        id_generator=SequenceIdGenerator(),
        event_hub=EventHub(),
    )


def create_request(request_id: str) -> CreateRunRequestV1:
    """构造明确联网的运营请求。"""
    return CreateRunRequestV1(
        request_id=request_id,
        tenant_id="tenant-1",
        user_id="user-1",
        input_text="收集下周 AI 行业热点，整理成公众号、小红书和头条三种版本",
        requested_strategy=StrategyMode.MULTI_AGENT,
        strategy_payload_schema_version="operation-strategy-payload/1",
        strategy_payload={"operation_request": {"request": {}}},
    )


@pytest.mark.asyncio
async def test_plain_operation_graph_does_not_publish_inferred_phase_events() -> None:
    """未接入真实阶段报告器的普通图不得因输入文本自动出现阶段。"""
    service = operation_request("phase-success", OperationSuccessGraph())
    queued = await service.create_and_schedule(create_request("phase-success"))
    await service.wait_for_background_tasks()

    events = await service.event_hub.replay(queued.run_id, 0)
    names = [event.event for event in events]
    assert {
        "phase_started",
        "research_started",
        "research_completed",
        "content_generation_started",
        "content_generation_completed",
        "quality_checked",
    }.isdisjoint(names)
    assert names.index("deliverable") < names.index("stream_done")
    assert names[-1] == "stream_done"
    allowed = {"phase", "count", "duration_ms", "degraded", "error_code"}
    for event in events:
        if event.event in {
            "phase_started",
            "research_started",
            "research_completed",
            "content_generation_started",
            "content_generation_completed",
            "quality_checked",
        }:
            assert set(event.payload) <= allowed
            assert "prompt" not in event.payload
            assert "raw_response" not in event.payload
            assert "tool_args" not in event.payload


@pytest.mark.asyncio
async def test_bound_progress_payload_cannot_override_trusted_phase() -> None:
    """Harness 必须让窄端口的受控 phase 覆盖不可信 payload 同名键。"""

    service = operation_request("phase-trusted", OperationReportingGraph())
    queued = await service.create_and_schedule(create_request("phase-trusted"))
    await service.wait_for_background_tasks()

    events = await service.event_hub.replay(queued.run_id, 0)
    phases = [event for event in events if event.event == "phase_started"]
    assert len(phases) == 1
    assert phases[0].payload == {
        "completed": 0,
        "target": 1,
        "phase": "understanding_request",
    }


@pytest.mark.asyncio
async def test_bound_progress_is_isolated_and_deduplicated_per_run() -> None:
    """并发 Run 的 ContextVar 发布器不得串线，单 Run 同阶段只发送一次。"""

    service = operation_request("phase-concurrent", ConcurrentReportingGraph())
    first, second = await asyncio.gather(
        service.create_and_execute(create_request("phase-concurrent-a")),
        service.create_and_execute(create_request("phase-concurrent-b")),
    )

    assert first.run_id != second.run_id
    for run_id in (first.run_id, second.run_id):
        events = await service.event_hub.replay(run_id, 0)
        phases = [event for event in events if event.event == "phase_started"]
        assert len(phases) == 1
        assert phases[0].run_id == run_id
        assert phases[0].payload["phase"] == "understanding_request"


@pytest.mark.asyncio
async def test_operation_failure_emits_safe_user_error_without_internal_exception() -> (
    None
):
    """研究或图执行失败时只发送固定用户级错误，不泄露异常正文。"""
    service = operation_request("phase-failure", OperationFailureGraph())
    queued = await service.create_and_schedule(create_request("phase-failure"))
    await service.wait_for_background_tasks()

    events = await service.event_hub.replay(queued.run_id, 0)
    errors = [event for event in events if event.event == "stream_error"]
    assert len(errors) == 1
    assert errors[0].payload["code"] == "GRAPH_EXECUTION_FAILED"
    assert "rendered_prompt" not in str(errors[0].payload)
    assert "provider raw response" not in str(errors[0].payload)
    assert not any(event.event == "phase_started" for event in events)
    assert events[-1].event == "stream_done"
