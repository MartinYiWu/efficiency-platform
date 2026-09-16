"""验证运营 Run 的阶段事件和用户级错误不会泄露内部细节。"""

from __future__ import annotations

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
                                        (("channel", "wechat"), ("content", "公众号成品"))
                                    ),
                                    JsonObject(
                                        (
                                            ("channel", "xiaohongshu"),
                                            ("content", "小红书成品"),
                                        )
                                    ),
                                    JsonObject(
                                        (("channel", "toutiao"), ("content", "头条成品"))
                                    ),
                                ),
                            ),
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
async def test_operation_run_publishes_ordered_phase_events_without_internal_details() -> None:
    """研究和生成阶段按顺序输出安全摘要，不得携带 Prompt 或模型原文。"""
    service = operation_request("phase-success", OperationSuccessGraph())
    queued = await service.create_and_schedule(create_request("phase-success"))
    await service.wait_for_background_tasks()

    events = await service.event_hub.replay(queued.run_id, 0)
    names = [event.event for event in events]
    assert names.index("phase_started") < names.index("research_started")
    assert names.index("research_started") < names.index("research_completed")
    assert names.index("research_completed") < names.index("content_generation_started")
    assert names.index("content_generation_started") < names.index(
        "content_generation_completed"
    )
    assert names.index("content_generation_completed") < names.index("quality_checked")
    assert names.index("quality_checked") < names.index("deliverable")
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
async def test_operation_failure_emits_safe_user_error_without_internal_exception() -> None:
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
    assert events[-1].event == "stream_done"
