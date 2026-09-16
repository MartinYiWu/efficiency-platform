"""运营 Specialist 的最小离线运行骨架。"""

from __future__ import annotations

from abc import ABC

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    DeliverableKind,
    GenerationProcessReference,
    OperationDeliverable,
)
from efficiency_platform_agent.agents.operation.specialists.contracts import (
    SpecialistExecutionResult,
)
from efficiency_platform_agent.agents.operation.specialists.runtime import (
    decode_specialist_task,
    encode_specialist_result,
)
from efficiency_platform_agent.core.agent import AgentSpec
from efficiency_platform_agent.core.enums import AgentKind, StrategyMode
from efficiency_platform_agent.core.multi_agent import BudgetUsage
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    ExtensionDescriptor,
    JsonObject,
    RunResult,
    SupervisorTask,
)


class OperationSpecialistBase(ABC):
    """提供统一 AgentPlugin 元数据和无外部依赖的结果构造。"""

    def __init__(
        self,
        *,
        agent_id: str,
        capability_id: str,
        task_type: str,
        prompt_bundle_id: str,
        quality_policy_id: str,
        output_title: str,
        output_label: str,
        strategy: StrategyMode = StrategyMode.DIRECT,
        allowed_tools: frozenset[str] = frozenset(),
        permissions: frozenset[str] = frozenset(),
        max_iterations: int = 2,
        max_tool_calls: int = 0,
        max_input_tokens: int = 7_000,
        max_output_tokens: int = 4_000,
        timeout_ms: int = 30_000,
        max_cost_microunits: int = 0,
        output_kind: DeliverableKind = DeliverableKind.PLAN,
    ) -> None:
        budget = ExecutionBudget(
            max_iterations,
            max_tool_calls,
            max_input_tokens,
            max_output_tokens,
            timeout_ms,
            max_cost_microunits,
        )
        self.spec = AgentSpec(
            agent_id=agent_id,
            semantic_version="1.0.0",
            owner="operation-specialists",
            kind=AgentKind.SPECIALIST,
            capability_ids=frozenset({capability_id}),
            supported_task_types=frozenset({task_type}),
            input_schema_version="operation-specialist-input/1",
            output_schema_version="operation-specialist-result/1",
            state_schema_version=f"{agent_id}-state/1",
            checkpoint_version=f"{agent_id}-checkpoint/1",
            allowed_strategies=frozenset({strategy}),
            prompt_bundle_id=prompt_bundle_id,
            allowed_tools=allowed_tools,
            knowledge_scopes=frozenset(),
            memory_policy_id="operation-specialist-memory/1",
            model_policy_id="s5-fake-model/1",
            quality_policy_id=quality_policy_id,
            permissions=permissions,
            budget=budget,
            termination_conditions=frozenset({"succeeded", "failed"}),
        )
        self.descriptor = ExtensionDescriptor(
            name=agent_id,
            semantic_version=self.spec.semantic_version,
            input_schema_version=self.spec.input_schema_version,
            output_schema_version=self.spec.output_schema_version,
            permissions=self.spec.permissions,
            budget=self.spec.budget,
            termination_conditions=self.spec.termination_conditions,
            checkpoint_version=self.spec.checkpoint_version,
        )
        self._output_title = output_title
        self._output_label = output_label
        self._output_kind = output_kind

    async def run(self, task: SupervisorTask) -> RunResult:
        """只消费 Supervisor 裁剪任务并返回版本化结果。"""

        try:
            execution_input = decode_specialist_task(task)
            result = self.build_result(execution_input)
        except ValueError as error:
            result = SpecialistExecutionResult(
                "operation-specialist-result/1",
                task.task_id,
                (),
                (task.task_id,),
                None,
                None,
                None,
                (),
                (),
                str(error).split(":", 1)[0],
                None,
                None,
                BudgetUsage(),
            )
        return encode_specialist_result(result, task.parent_run_id)

    def build_result(self, execution_input: object) -> SpecialistExecutionResult:
        """构造一个不访问外部系统的结构化策略交付物。"""

        task_id = getattr(execution_input, "task_id", "task")
        context = getattr(execution_input, "operation_context", None)
        profile_ids = tuple(
            ref.profile_id for ref in getattr(context, "profile_references", ())
        )
        deliverable = OperationDeliverable(
            "operation-deliverable/1",
            f"{self.spec.agent_id.replace('.', '-')}-{task_id}",
            self._output_kind,
            "1.0.0",
            self._output_title,
            (task_id,),
            (),
            None,
            JsonObject(
                (
                    ("scope", self.spec.agent_id),
                    ("deliverable_kind", self._output_label),
                    ("status", "draft"),
                )
            ),
            frozenset(),
            frozenset(),
            frozenset(),
            profile_ids,
            GenerationProcessReference(
                f"process-{task_id}", "operation-specialist-process/1", (), ()
            ),
            self.spec.prompt_bundle_id.replace(".", "-").replace("/", "-"),
            "1",
            f"plan-{task_id}",
            None,
            None,
        )
        from efficiency_platform_agent.agents.operation.contracts.deliverables import (
            DeliverableBundle,
        )

        bundle = DeliverableBundle(
            "deliverable-bundle/1",
            f"bundle-{task_id}",
            task_id,
            f"plan-{task_id}",
            (deliverable,),
            None,
            (),
            frozenset(),
        )
        return SpecialistExecutionResult(
            "operation-specialist-result/1",
            task_id,
            (self.spec.agent_id,),
            (),
            bundle,
            None,
            None,
            (),
            (),
            None,
            None,
            None,
            BudgetUsage(iterations=1),
        )


__all__ = ["OperationSpecialistBase"]
