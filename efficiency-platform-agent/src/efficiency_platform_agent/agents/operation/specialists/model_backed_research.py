"""把可信研究来源接入模型驱动交付物生成。"""

from __future__ import annotations

from dataclasses import replace

from efficiency_platform_agent.agents.operation.execution import OperationUsage
from efficiency_platform_agent.agents.operation.quality.evidence_gate import (
    EvidenceGate,
    EvidenceGatePolicy,
)
from efficiency_platform_agent.agents.operation.specialists.contracts import (
    SpecialistExecutionResult,
)
from efficiency_platform_agent.agents.operation.specialists.model_backed import (
    ModelBackedOperationSpecialist,
    evidence_citations,
    freeze,
    plain,
)
from efficiency_platform_agent.agents.operation.specialists.research import (
    ResearchInsightAgent,
)
from efficiency_platform_agent.agents.operation.specialists.runtime import (
    encode_specialist_result,
)
from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchProviderPort,
    ResearchRequest,
    ResearchStatus,
)
from efficiency_platform_agent.core.agent import AgentSpec
from efficiency_platform_agent.core.multi_agent import BudgetUsage
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    RunResult,
    SupervisorTask,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.prompts.runtime import PromptRuntime


class ModelBackedResearchSpecialist:
    """先检索可信来源，再把来源约束注入模型生成。"""

    def __init__(
        self,
        spec: AgentSpec,
        prompts: PromptRuntime,
        model: ModelRuntime,
        provider: ResearchProviderPort,
        usage: OperationUsage | None = None,
    ) -> None:
        if not isinstance(provider, ResearchProviderPort):
            raise TypeError("research_provider必须实现ResearchProviderPort")
        self.spec = spec
        self._provider = provider
        self._prompts = prompts
        self._model = model
        self._usage = usage
        self.descriptor = ModelBackedOperationSpecialist(
            spec, prompts, model, usage
        ).descriptor

    async def run(self, task: SupervisorTask) -> RunResult:
        """研究失败时返回显式失败，成功时只允许 Provider URL 进入模型。"""
        raw = plain(task.input_data)
        if not isinstance(raw, dict):
            raise TypeError("SPECIALIST_INPUT_INVALID")
        request = ResearchRequest(
            "research-request/1",
            f"research-{task.task_id}",
            task.task_id,
            str(raw["tenant_id"]),
            str(raw["goal"]),
            None,
            5,
            ("goal",),
            "research-result/1",
            task.budget.max_output_tokens,
        )
        result = await self._provider.research(request)
        if (
            result.request_id != request.request_id
            or result.task_id != request.task_id
            or result.tenant_id != request.tenant_id
        ):
            return self._failure(task, "EVIDENCE_INVALID", result.usage)
        if self._usage is not None:
            self._usage.record_snapshot(result.usage)
        # 研究失败优先保持研究错误语义；供应商失败响应中的异常 usage
        # 不能把无来源研究误判成预算耗尽。
        if result.status is not ResearchStatus.SUCCEEDED or not result.observations:
            return self._failure(task, "RESEARCH_UNAVAILABLE", result.usage)
        pack = ResearchInsightAgent._evidence_pack(task.task_id, result.observations)
        decision = EvidenceGate().evaluate(
            pack,
            frozenset({"goal"}),
            EvidenceGatePolicy("research-v1", 1, 1, True, True),
        )
        if not decision.accepted:
            return self._failure(
                task, decision.reason_codes[0] or "EVIDENCE_INVALID", result.usage
            )
        raw["citations"] = evidence_citations(pack)
        warnings = (
            ("EVIDENCE_UNVERIFIED",)
            if any(item.quality_status.value == "unverified" for item in pack.records)
            else ()
        )
        delegate = ModelBackedOperationSpecialist(
            self.spec,
            self._prompts,
            self._model,
            self._usage,
            pack,
            warnings,
            result.usage,
        )
        # Responses API 的 web_search 用量包含服务端搜索工具链上下文，不能
        # 直接从下游内容生成预算中扣除；真实用量仍已记录到当前 Run。
        # 这里只为内容生成保留独立的迭代、输入、输出和超时预算。
        remaining_budget = ExecutionBudget(
            max_iterations=max(1, task.budget.max_iterations - 1),
            max_tool_calls=task.budget.max_tool_calls,
            max_input_tokens=task.budget.max_input_tokens,
            max_output_tokens=task.budget.max_output_tokens,
            timeout_ms=task.budget.timeout_ms,
            max_cost_microunits=task.budget.max_cost_microunits,
        )
        frozen = freeze(raw)
        if not isinstance(frozen, JsonObject):
            raise TypeError("SPECIALIST_INPUT_INVALID")
        return await delegate.run(
            replace(task, input_data=frozen, budget=remaining_budget)
        )

    @staticmethod
    def _failure(task: SupervisorTask, code: str, usage: UsageSnapshot) -> RunResult:
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
            code,
            None,
            None,
            BudgetUsage(
                iterations=1 if usage != UsageSnapshot() else 0,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_microunits=usage.cost_microunits,
            ),
        )
        return encode_specialist_result(result, task.parent_run_id)


__all__ = ["ModelBackedResearchSpecialist"]
