"""节点局部执行结果和可信模型用量，不属于入站或前端契约。"""

from dataclasses import dataclass, field

from efficiency_platform_agent.agents.operation.scenarios.contracts import (
    ScenarioExecutionResult,
)
from efficiency_platform_agent.contracts.deliverables import (
    DeliverableSetV1,
    DeliverableSetV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    ResearchBriefV2,
    ResearchOutcomeV2,
)
from efficiency_platform_agent.core.model import ModelExecutionResult
from efficiency_platform_agent.core.multi_agent import CompletionStatus
from efficiency_platform_agent.core.runtime import UsageSnapshot


@dataclass
class OperationUsage:
    """每次 Run 独立创建，记录 Provider 返回后所有尝试的可信用量。"""

    executions: list[ModelExecutionResult] = field(default_factory=list)
    capability_usage: list[UsageSnapshot] = field(default_factory=list)
    research_results: dict[
        tuple[str, str], tuple[ResearchBriefV2, ResearchOutcomeV2]
    ] = field(default_factory=dict)
    research_request_ids: dict[tuple[str, str], str] = field(default_factory=dict)

    def record_research(
        self, request_id: str, brief: ResearchBriefV2, outcome: ResearchOutcomeV2
    ) -> None:
        """只保存当前 Run 的受控研究事实，不从模型输出反推。"""
        key = (brief.trusted_context.tenant_id, brief.trusted_context.task_id)
        self.research_results[key] = (brief, outcome)
        self.research_request_ids[key] = request_id

    def record(self, execution: ModelExecutionResult) -> None:
        """在业务输出校验前记账，失败成品也不得免除模型消耗。"""
        self.executions.append(execution)

    def record_snapshot(self, usage: UsageSnapshot) -> None:
        """记录非模型能力返回的可信用量。"""
        self.capability_usage.append(usage)

    def snapshot(self) -> UsageSnapshot:
        """对并行专家结果求和，保留估算标记。"""
        return UsageSnapshot(
            sum(item.usage.input_tokens for item in self.executions)
            + sum(item.input_tokens for item in self.capability_usage),
            sum(item.usage.output_tokens for item in self.executions)
            + sum(item.output_tokens for item in self.capability_usage),
            sum(item.usage.cost_microunits for item in self.executions)
            + sum(item.cost_microunits for item in self.capability_usage),
            any(item.usage.estimated for item in self.executions)
            or any(item.estimated for item in self.capability_usage),
        )


@dataclass(frozen=True)
class OperationExecution:
    """图节点消费的结果，保持 S6 契约原样并显式携带用量。"""

    deliverables: DeliverableSetV1 | DeliverableSetV2 | None
    status: CompletionStatus
    usage: UsageSnapshot
    error_code: str | None = None
    scenario_result: ScenarioExecutionResult | None = None
    quality_check_report_ids: dict[str, str] = field(default_factory=dict)
