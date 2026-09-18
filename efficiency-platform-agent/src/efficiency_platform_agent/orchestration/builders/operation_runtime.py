"""将运营场景接线注册到 S2 唯一 GraphRuntime。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph

from efficiency_platform_agent.agents.operation.contracts.task import OperationRequest
from efficiency_platform_agent.agents.operation.operation_agent import OperationAgent
from efficiency_platform_agent.agents.operation.scenarios.contracts import (
    ScenarioSubmission,
)
from efficiency_platform_agent.agents.operation.specialists.model_backed import (
    plain,
)
from efficiency_platform_agent.contracts.deliverables import DeliverableSetV2
from efficiency_platform_agent.contracts.operation_strategy import (
    OperationStrategyPayloadAdapter,
    decode_operation_request,
)
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.operation_progress import (
    report_operation_progress,
)
from efficiency_platform_agent.core.run import JsonObject
from efficiency_platform_agent.orchestration.builders.operation_supervisor import (
    _CompiledOperationGraph,
    _OperationGraphState,
)
from efficiency_platform_agent.orchestration.contracts import GraphRegistration

SubmissionResolver = Callable[
    [OperationRequest, dict[str, Any]], Awaitable[ScenarioSubmission]
]


class OperationRuntimeGraphBuilder:
    """只构建图程序，不创建 Harness 或运行第二条生命周期。"""

    def __init__(self, agent: OperationAgent, submission_resolver: SubmissionResolver):
        self.agent = agent
        self.submission_resolver = submission_resolver
        self.checkpointer = InMemorySaver()

    def build(self):
        """模型输出和领域对象只留在节点局部变量，检查点仅含 JSON。"""
        graph = StateGraph(_OperationGraphState)

        async def execute(state):
            payload = state["strategy_payload"]
            if isinstance(payload, JsonObject):
                payload = plain(payload)
            if not isinstance(payload, dict) or set(payload) != {"operation_request"}:
                raise ValueError("PRECOMPUTED_STATE_FORBIDDEN")
            request = decode_operation_request(payload["operation_request"])
            if (
                request.request.tenant_id != state["tenant_id"]
                or request.request.user_id != state["user_id"]
            ):
                raise ValueError("OPERATION_IDENTITY_MISMATCH")
            submission = await self.submission_resolver(request, state)
            if (
                submission.request.request.tenant_id != request.request.tenant_id
                or submission.request.request.user_id != request.request.user_id
            ):
                raise ValueError("SCENARIO_IDENTITY_MISMATCH")
            await report_operation_progress("understanding_request")
            try:
                execution = await self.agent.execute(submission, run_id=state["run_id"])
            except ValueError as error:
                code = str(error)
                if code == "OPERATION_CANCELLED":
                    return {"next_status": "cancelled", "output": None}
                if code == "SCENARIO_INPUT_REQUIRED":
                    return {"next_status": "waiting_input", "output": None}
                if code in {
                    "RESEARCH_UNAVAILABLE",
                    "RESEARCH_INSUFFICIENT",
                    "EVIDENCE_INVALID",
                }:
                    return {
                        "next_status": "failed",
                        "error_code": "RESEARCH_UNAVAILABLE",
                        "output": None,
                    }
                # 固定错误白名单防止把异常正文写入 Graph State 或 SSE。
                return {
                    "next_status": "failed",
                    "error_code": "OPERATION_EXECUTION_FAILED",
                    "output": None,
                }
            usage = {
                "input_tokens": execution.usage.input_tokens,
                "output_tokens": execution.usage.output_tokens,
                "cost_microunits": execution.usage.cost_microunits,
                "estimated": execution.usage.estimated,
            }
            result = execution.deliverables
            if result is None:
                status = {
                    "cancelled": "cancelled",
                    "waiting_input": "waiting_input",
                }.get(execution.status.value, "failed")
                return {
                    "next_status": status,
                    "output": None,
                    "error_code": execution.error_code,
                    "usage": usage,
                }
            return {
                "next_status": "succeeded",
                "output": {
                    "delivery_contract_version": result.contract_version,
                    "content": result.summary.message
                    if isinstance(result, DeliverableSetV2)
                    else result.summary,
                    "deliverable_set": result.model_dump(mode="json"),
                    "quality_report": asdict(execution.scenario_result.quality_report)
                    if execution.scenario_result
                    and execution.scenario_result.quality_report
                    else None,
                    "quality_report_ids": list(
                        execution.scenario_result.deliverable_bundle.quality_report_ids
                    )
                    if execution.scenario_result
                    and execution.scenario_result.deliverable_bundle
                    else [],
                    "quality_check_report_ids": execution.quality_check_report_ids,
                },
                "degraded": result.degraded,
                "usage": usage,
            }

        graph.add_node("operation_scenario", execute)
        graph.set_entry_point("operation_scenario")
        graph.add_edge("operation_scenario", END)
        return _CompiledOperationGraph(graph.compile(checkpointer=self.checkpointer))


def build_operation_multi_agent_registration(
    agent: OperationAgent, submission_resolver: SubmissionResolver
) -> GraphRegistration:
    """供组合根显式登记 MULTI_AGENT，不修改既有 S2 策略载荷契约。"""
    adapter = OperationStrategyPayloadAdapter()
    return GraphRegistration(
        graph_id="operation-conversation",
        strategy=StrategyMode.MULTI_AGENT,
        graph_version="1.0.0",
        checkpoint_ns="s2:multi_agent:1",
        strategy_payload_schema_version=adapter.schema_version,
        allowed_strategy_payload_keys=adapter.allowed_keys,
        allowed_next_statuses=frozenset(
            {
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.WAITING_INPUT,
            }
        ),
        builder=OperationRuntimeGraphBuilder(agent, submission_resolver),
        payload_adapter=adapter,
    )


__all__ = ["OperationRuntimeGraphBuilder", "build_operation_multi_agent_registration"]
