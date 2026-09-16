"""供 S4 Supervisor 单元测试使用的合成注册项与任务节点。"""

from __future__ import annotations

from dataclasses import replace

from efficiency_platform_agent.agents.registry import AgentRegistry
from efficiency_platform_agent.core.agent import AgentSpec
from efficiency_platform_agent.core.multi_agent import TaskNode
from efficiency_platform_agent.core.ports import AgentPlugin
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject

from .agent_fakes import build_synthetic_agent, build_synthetic_spec


def build_specialist_spec(
    agent_id: str,
    *,
    capability_ids: frozenset[str] = frozenset({"synthetic.compose"}),
    supported_task_types: frozenset[str] = frozenset({"synthetic.compose"}),
    input_schema_version: str = "synthetic-input/1",
    output_schema_version: str = "synthetic-output/1",
    allowed_tools: frozenset[str] = frozenset({"synthetic.read"}),
    permissions: frozenset[str] = frozenset({"public.read"}),
) -> AgentSpec:
    """构造只包含合成能力的 Specialist 元数据。"""
    base = build_synthetic_spec(agent_id=agent_id, capability_ids=capability_ids)
    return replace(
        base,
        supported_task_types=supported_task_types,
        input_schema_version=input_schema_version,
        output_schema_version=output_schema_version,
        allowed_tools=allowed_tools,
        permissions=permissions,
        prompt_bundle_id="synthetic.prompt",
    )


def register_specialists(
    specs: tuple[AgentSpec, ...],
) -> AgentRegistry:
    """把合成 Agent 注册到真实 Registry 实例，不建立外部连接。"""
    registry = AgentRegistry()
    for spec in specs:

        def builder(spec: AgentSpec = spec) -> AgentPlugin:
            """构造当前注册项的合成实例。"""
            return build_synthetic_agent(spec)

        registry.register(spec, builder)
    return registry


def build_task_node(
    *,
    task_id: str = "synthetic-task",
    capability: str = "synthetic.compose",
    task_type: str = "synthetic.compose",
    input_schema_version: str = "synthetic-input/1",
    output_schema_version: str = "synthetic-output/1",
    allowed_tools: frozenset[str] = frozenset({"synthetic.read"}),
    required_permissions: frozenset[str] = frozenset({"public.read"}),
) -> TaskNode:
    """构造供选择和派发测试使用的不可变节点。"""
    from efficiency_platform_agent.core.agent import CapabilityRequirement
    from efficiency_platform_agent.core.multi_agent import TaskFailureMode

    budget = ExecutionBudget(3, 2, 100, 100, 30_000, 10)
    return TaskNode(
        task_id=task_id,
        task_type=task_type,
        capability_requirement=CapabilityRequirement(all_of=frozenset({capability})),
        input_schema_version=input_schema_version,
        output_schema_version=output_schema_version,
        depends_on=(),
        required=True,
        failure_mode=TaskFailureMode.FAIL_PLAN,
        input_reference_ids=(),
        context_view=JsonObject((("input", "synthetic"),)),
        allowed_tools=allowed_tools,
        required_permissions=required_permissions,
        requested_budget=budget,
        expected_deliverable_ids=("synthetic-deliverable",),
        quality_check_ids=frozenset(),
    )
