"""真实模型运营专家的显式组合，不读取配置或创建外部 SDK。"""

from dataclasses import replace
from typing import Any, Literal

from efficiency_platform_agent.agents.operation.definition import operation_agent_specs
from efficiency_platform_agent.agents.operation.execution import OperationUsage
from efficiency_platform_agent.agents.operation.operation_agent import OperationAgent
from efficiency_platform_agent.agents.operation.specialists.model_backed import (
    ModelBackedOperationSpecialist,
)
from efficiency_platform_agent.agents.operation.specialists.model_backed_research import (
    ModelBackedResearchSpecialist,
)
from efficiency_platform_agent.agents.registry import AgentRegistry
from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchProviderPort,
    ResearchRequest,
    ResearchResult,
    ResearchStatus,
)
from efficiency_platform_agent.core.diagnostics import (
    DiagnosticLevel,
    DiagnosticRecord,
    DiagnosticRecorderPort,
    NoopDiagnosticRecorder,
)
from efficiency_platform_agent.core.run import ExecutionBudget
from efficiency_platform_agent.harness.research_v2_adapter import (
    ResearchV2ProviderAdapter,
)
from efficiency_platform_agent.orchestration.supervisor import ScenarioSupervisorAdapter
from efficiency_platform_agent.prompts.contracts import PromptBundleSpec
from efficiency_platform_agent.prompts.registry import PromptRegistry
from efficiency_platform_agent.prompts.runtime import PromptRuntime


class _UnavailableResearchProvider:
    """研究能力未启用时返回透明失败，阻止普通专家绕过证据门。"""

    def __init__(
        self,
        recorder: DiagnosticRecorderPort,
        reason_code: str,
    ) -> None:
        self._recorder = recorder
        self._reason_code = reason_code

    async def research(self, request: ResearchRequest) -> ResearchResult:
        """保留安全失败契约，同时输出能力未装配的稳定原因。"""

        try:
            self._recorder.record(
                DiagnosticRecord(
                    event_name="research_invocation_failed",
                    component="provider",
                    level=DiagnosticLevel.ERROR,
                    capability="deepseek_web_search",
                    stage="capability.resolve",
                    provider="deepseek_web_search",
                    error_code=self._reason_code,
                    retryable=False,
                    attempt=1,
                )
            )
        except Exception:  # noqa: BLE001, 诊断不得改变研究安全失败契约
            return self._failed_result(request)
        return self._failed_result(request)

    def _failed_result(self, request: ResearchRequest) -> ResearchResult:
        """集中构造不向上泄漏内部诊断原因的研究失败结果。"""

        return ResearchResult(
            "research-result/1",
            request.request_id,
            request.task_id,
            request.tenant_id,
            ResearchStatus.FAILED,
            (),
            ("在线研究能力当前不可用",),
            "RESEARCH_UNAVAILABLE",
        )


def build_operation_prompt_registry() -> PromptRegistry:
    """显式注册运营成品的 V1 与 V2 Prompt。"""
    prompt_registry = PromptRegistry()
    prompt_registry.register(
        PromptBundleSpec(
            "operation.deliverable.generation/1",
            "1.0.0",
            "operation",
            "operation/deliverable_generation_v1.j2",
            "operation-prompt/1",
            frozenset({"capability"}),
            "deliverable/1",
            frozenset({"balanced"}),
            20000,
        )
    )
    prompt_registry.register(
        PromptBundleSpec(
            "operation.deliverable.generation/2",
            "1.0.0",
            "operation",
            "operation/deliverable_generation_v2.j2",
            "operation-prompt/2",
            frozenset({"capability", "deliverable_kind"}),
            "deliverable/2",
            frozenset({"balanced"}),
            30_000,
        )
    )
    return prompt_registry


def build_operation_agent(
    model: ModelRuntime,
    *,
    budget: ExecutionBudget | None = None,
    cancellation: Any = None,
    research_provider: ResearchProviderPort | None = None,
    diagnostic_recorder: DiagnosticRecorderPort | None = None,
    research_unavailable_code: str = "RESEARCH_PROVIDER_NOT_CONFIGURED",
    deliverable_set_contract_version: Literal[
        "deliverable-set/1", "deliverable-set/2"
    ] = "deliverable-set/2",
) -> OperationAgent:
    """显式注册模型专家，再把 Supervisor 窄端口注入业务 Agent。"""
    if deliverable_set_contract_version not in {
        "deliverable-set/1",
        "deliverable-set/2",
    }:
        raise ValueError("DELIVERABLE_SET_VERSION_UNSUPPORTED")
    specialist_version = (
        "deliverable/2"
        if deliverable_set_contract_version == "deliverable-set/2"
        else "deliverable/1"
    )
    prompts = PromptRuntime(build_operation_prompt_registry())
    resolved_budget = budget or ExecutionBudget(40, 10, 64000, 32000, 180000, 1000000)
    recorder = diagnostic_recorder or NoopDiagnosticRecorder()
    resolved_research_provider = research_provider or _UnavailableResearchProvider(
        recorder, research_unavailable_code
    )
    governed_research_v2 = isinstance(
        resolved_research_provider, ResearchV2ProviderAdapter
    )

    def supervisor_factory(
        run_id: str | None, usage: OperationUsage
    ) -> ScenarioSupervisorAdapter:
        """注册表和用量收集器只属于当前运行，防止并发 Run 串账。"""
        registry = AgentRegistry()
        run_research = (
            resolved_research_provider.for_run(run_id, usage.record_research)
            if isinstance(resolved_research_provider, ResearchV2ProviderAdapter)
            else resolved_research_provider
        )
        for definition in operation_agent_specs():
            spec = replace(definition, model_policy_id="operation-runtime-model/1")

            def builder(spec=spec):
                if spec.agent_id == "operation.research.insight":
                    return ModelBackedResearchSpecialist(
                        spec,
                        prompts,
                        model,
                        run_research,
                        usage,
                        deliverable_contract_version=specialist_version,
                    )
                return ModelBackedOperationSpecialist(
                    spec,
                    prompts,
                    model,
                    usage,
                    deliverable_contract_version=specialist_version,
                )

            registry.register(spec, builder)
        return ScenarioSupervisorAdapter(
            registry,
            budget=resolved_budget,
            cancellation=cancellation,
            run_id=run_id,
            diagnostic_recorder=recorder,
            research_provider=run_research,
            usage=usage,
        )

    return OperationAgent(
        supervisor_factory,
        research_provider=resolved_research_provider,
        deliverable_set_contract_version=deliverable_set_contract_version,
        governed_research_v2=governed_research_v2,
    )
