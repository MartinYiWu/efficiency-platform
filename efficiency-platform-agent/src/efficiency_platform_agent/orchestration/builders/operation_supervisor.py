"""唯一运营 Supervisor 图构建器；LangGraph 仅允许在本模块出现。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from itertools import pairwise
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from efficiency_platform_agent.core.run import JsonObject
from efficiency_platform_agent.strategies.multi_agent.nodes import (
    SupervisorDependencies,
    aggregate_node,
    assemble_node,
    build_operation_context_node,
    build_plan_node,
    cancel_node,
    compile_plan_node,
    decode_operation_request_node,
    initialize_budget_node,
    normalize_intent_node,
    reconcile_wave_node,
    schedule_wave_node,
    wait_input_node,
)
from efficiency_platform_agent.strategies.multi_agent.routing import (
    route_after_aggregate,
    route_after_reconcile,
)

NODE_SEQUENCE = (
    "decode_operation_request",
    "normalize_intent",
    "evaluate_input",
    "build_operation_context",
    "build_plan",
    "compile_plan",
    "initialize_budget",
    "schedule_wave",
    "reconcile_wave",
    "aggregate",
    "assemble",
    "finalize",
)

BRANCH_NODES = ("schedule_wave", "wait_input", "aggregate", "cancel", "fail")


def _json_plain(value: object) -> object:
    """将图边界值归一化为 MsgPack 可安全处理的 JSON 基础值。"""

    if isinstance(value, JsonObject):
        return {key: _json_plain(child) for key, child in value.items}
    if isinstance(value, Enum):
        return _json_plain(value.value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (tuple, list)):
        return [_json_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_plain(item) for key, item in value.items()}
    if is_dataclass(value):
        return {
            field.name: _json_plain(getattr(value, field.name))
            for field in fields(value)
        }
    raise TypeError("图状态只能包含 JSON 基础值")


class _OperationGraphState(TypedDict, total=False):
    """Supervisor 图需要保留的 S2 基础字段与 S4 运行字段。"""

    run_id: str
    tenant_id: str
    user_id: str
    request_id: str
    input_text: str
    strategy: str
    workflow_id: str | None
    strategy_payload_schema_version: str
    strategy_payload: JsonObject
    allowed_tools: list[str]
    estimated_input_tokens: int
    prompt_id: str | None
    tool_output: object
    model_attempts: list[dict[str, object]]
    runtime_facts: list[dict[str, object]]
    usage: dict[str, object]
    budget_state: dict[str, object]
    output: object
    error_code: str | None
    degraded: bool
    test_mode: str | None
    next_status: str | None
    operation_request: object
    operation_task: object
    operation_context: object
    operation_plan: object
    plan_id: str | None
    plan_contract_version: str | None
    plan_revision: int
    task_graph: object
    task_statuses: dict[str, str]
    attempts: dict[str, int]
    task_revisions: dict[str, int]
    fence_token: int
    budget_ledger: dict[str, object]
    outcomes: dict[str, object]
    wave_events: list[object]
    pending_input: object
    cancel_requested: bool
    resume_value: object
    completion_status: str | None
    resume_binding: object


class _CompiledOperationGraph:
    """将 LangGraph 编译结果适配为 S2 GraphProgram。"""

    def __init__(self, graph) -> None:
        self._graph = graph

    async def invoke(self, initial_state, config: Mapping[str, object]):
        return await self._graph.ainvoke(_json_plain(initial_state), config)

    async def resume(self, resume_value, config: Mapping[str, object]):
        return await self._graph.ainvoke(Command(resume=resume_value), config)

    async def get_state(self, config: Mapping[str, object]):
        return self._graph.get_state(config).values


class OperationSupervisorGraphBuilder:
    """通过依赖闭包构建运营 Supervisor 图，不改变 S2 runtime。"""

    def __init__(self, dependencies: SupervisorDependencies, limits=None) -> None:
        self.dependencies = dependencies
        self.limits = limits
        self.checkpointer = InMemorySaver()
        self.node_sequence = NODE_SEQUENCE

    def build(self):
        graph = StateGraph(_OperationGraphState)
        dep = self.dependencies

        def sync(node):
            """保留未被当前节点修改的 JSON 状态键。"""

            def invoke(state):
                patch = node(state, dep)
                normalized = _json_plain(patch)
                if not isinstance(normalized, dict):
                    raise TypeError("节点补丁必须是 JSON 对象")
                return {**state, **normalized}

            return invoke

        async def async_schedule(state):
            patch = await schedule_wave_node(state, dep)
            normalized = _json_plain(patch)
            if not isinstance(normalized, dict):
                raise TypeError("节点补丁必须是 JSON 对象")
            return {**state, **normalized}

        graph.add_node("decode_operation_request", sync(decode_operation_request_node))
        graph.add_node("normalize_intent", sync(normalize_intent_node))
        graph.add_node("evaluate_input", lambda s: dict(s))
        graph.add_node("build_operation_context", sync(build_operation_context_node))
        graph.add_node("build_plan", sync(build_plan_node))
        graph.add_node("compile_plan", sync(compile_plan_node))
        graph.add_node("initialize_budget", sync(initialize_budget_node))
        graph.add_node("schedule_wave", async_schedule)
        graph.add_node("reconcile_wave", sync(reconcile_wave_node))
        graph.add_node("aggregate", sync(aggregate_node))
        graph.add_node("assemble", sync(assemble_node))
        graph.add_node("wait_input_prepare", sync(wait_input_node))

        def interrupt_wait_input(state):
            """在已保存等待状态后挂起，并在恢复时返回补充值。"""

            resume_value = interrupt(state.get("pending_input") or {"required": True})
            return {
                "resume_value": _json_plain(resume_value),
                "pending_input": None,
                "next_status": None,
                "completion_status": None,
            }

        graph.add_node("wait_input", interrupt_wait_input)
        graph.add_node("cancel", sync(cancel_node))
        graph.add_node(
            "fail",
            lambda s: {
                **s,
                "next_status": "failed",
                "error_code": "SUPERVISOR_FAILED",
            },
        )
        graph.add_node(
            "finalize",
            lambda s: {
                **s,
                "next_status": "succeeded",
                "output": s.get(
                    "output", JsonObject((("content", "运营 Supervisor 已完成"),))
                ),
            },
        )
        for left, right in pairwise(NODE_SEQUENCE):
            if left in {"reconcile_wave", "aggregate"}:
                continue
            graph.add_edge(left, right)
        graph.add_conditional_edges(
            "reconcile_wave",
            route_after_reconcile,
            {
                "schedule_wave": "schedule_wave",
                "wait_input": "wait_input_prepare",
                "aggregate": "aggregate",
                "cancel": "cancel",
                "fail": "fail",
            },
        )
        graph.add_conditional_edges(
            "aggregate",
            route_after_aggregate,
            {
                "wait_input": "wait_input_prepare",
                "cancel": "cancel",
                "fail": "fail",
                "assemble": "assemble",
            },
        )
        graph.add_edge("wait_input_prepare", "wait_input")
        graph.add_conditional_edges(
            "wait_input",
            lambda state: "schedule_wave" if "resume_value" in state else "end",
            {"schedule_wave": "schedule_wave", "end": END},
        )
        graph.add_edge("cancel", END)
        graph.add_edge("fail", END)
        graph.set_entry_point(NODE_SEQUENCE[0])
        graph.add_edge("finalize", END)
        return _CompiledOperationGraph(graph.compile(checkpointer=self.checkpointer))


def build_operation_supervisor_graph(dependencies: SupervisorDependencies, limits=None):
    """构建唯一运营 Supervisor GraphProgram。"""

    return OperationSupervisorGraphBuilder(dependencies, limits).build()


__all__ = [
    "BRANCH_NODES",
    "NODE_SEQUENCE",
    "OperationSupervisorGraphBuilder",
    "build_operation_supervisor_graph",
]
