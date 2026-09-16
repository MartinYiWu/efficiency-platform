from __future__ import annotations

from dataclasses import dataclass

from efficiency_platform_agent.core.agent import AgentSpec
from efficiency_platform_agent.core.enums import AgentKind, RunStatus, StrategyMode
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    ExtensionDescriptor,
    JsonObject,
    RunResult,
    SupervisorTask,
)


def build_synthetic_spec(
    agent_id: str = "synthetic_research_agent",
    capability_ids: frozenset[str] = frozenset({"public_research"}),
) -> AgentSpec:
    """构造不包含真实业务和外部配置的合成 Agent 定义。"""

    return AgentSpec(
        agent_id=agent_id,
        semantic_version="1.0.0",
        owner="agent_platform",
        kind=AgentKind.SPECIALIST,
        capability_ids=capability_ids,
        supported_task_types=frozenset({"research"}),
        input_schema_version="research-task/1",
        output_schema_version="research-result/1",
        state_schema_version="research-state/1",
        checkpoint_version="research-checkpoint/1",
        allowed_strategies=frozenset({StrategyMode.REACT}),
        prompt_bundle_id="research_prompt/1",
        allowed_tools=frozenset({"public_search"}),
        knowledge_scopes=frozenset({"public"}),
        memory_policy_id="specialist_memory/1",
        model_policy_id="adaptive_model/1",
        quality_policy_id="research_quality/1",
        permissions=frozenset({"public_web.read"}),
        budget=ExecutionBudget(
            max_iterations=3,
            max_tool_calls=2,
            max_input_tokens=2_000,
            max_output_tokens=1_000,
            timeout_ms=30_000,
            max_cost_microunits=0,
        ),
        termination_conditions=frozenset({"succeeded", "failed"}),
    )


@dataclass(slots=True)
class SyntheticAgent:
    """只用于离线契约测试的合成 Specialist。"""

    descriptor: ExtensionDescriptor
    spec: AgentSpec

    async def run(self, task: SupervisorTask) -> RunResult:
        """返回不访问任何外部系统的确定性合成结果。"""

        return RunResult(
            run_id=task.parent_run_id,
            status=RunStatus.SUCCEEDED,
            strategy=StrategyMode.MULTI_AGENT,
            output=JsonObject((('task_id', task.task_id),)),
        )


def build_synthetic_agent(
    spec: AgentSpec | None = None,
    *,
    descriptor_name: str | None = None,
) -> SyntheticAgent:
    """按 AgentSpec 构造可测试实例，并允许显式制造名称不一致。"""

    resolved_spec = spec or build_synthetic_spec()
    descriptor = ExtensionDescriptor(
        name=descriptor_name or resolved_spec.agent_id,
        semantic_version=resolved_spec.semantic_version,
        input_schema_version=resolved_spec.input_schema_version,
        output_schema_version=resolved_spec.output_schema_version,
        permissions=resolved_spec.permissions,
        budget=resolved_spec.budget,
        termination_conditions=resolved_spec.termination_conditions,
        checkpoint_version=resolved_spec.checkpoint_version,
    )
    return SyntheticAgent(descriptor=descriptor, spec=resolved_spec)
