"""运营总 Agent 的场景接线，供统一 Graph Runtime 内部节点调用。"""

from __future__ import annotations

from collections.abc import Callable

from efficiency_platform_agent.agents.operation.execution import (
    OperationExecution,
    OperationUsage,
)
from efficiency_platform_agent.agents.operation.scenarios.contracts import (
    ScenarioQualityGate,
    ScenarioSubmission,
    ScenarioSupervisorPort,
)
from efficiency_platform_agent.agents.operation.scenarios.manifests import (
    build_s6_manifests,
)
from efficiency_platform_agent.agents.operation.scenarios.registry import (
    InMemoryScenarioPackRegistry,
)
from efficiency_platform_agent.agents.operation.scenarios.runtime_quality import (
    RuntimeScenarioQualityGate,
)
from efficiency_platform_agent.agents.operation.scenarios.service import (
    ScenarioPackService,
)
from efficiency_platform_agent.agents.operation.specialists.model_backed import (
    plain,
)
from efficiency_platform_agent.capabilities.quality.deliverable_assembler import (
    DeliverableAssembler,
)
from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchProviderPort,
)
from efficiency_platform_agent.contracts.deliverables import DeliverableSetV1
from efficiency_platform_agent.core.multi_agent import CompletionStatus


class OperationAgent:
    """连接 S6 服务和 S4 中央调度，返回严格前端成品集合。"""

    def __init__(
        self,
        supervisor_factory: Callable[
            [str | None, OperationUsage], ScenarioSupervisorPort
        ],
        quality_gate: ScenarioQualityGate | None = None,
        research_provider: ResearchProviderPort | None = None,
    ):
        self.supervisor_factory = supervisor_factory
        self.research_provider = research_provider
        self.scenarios = InMemoryScenarioPackRegistry(build_s6_manifests())
        self.assembler = DeliverableAssembler()
        self.quality_gate = quality_gate or RuntimeScenarioQualityGate()

    async def handle(
        self, submission: ScenarioSubmission, *, run_id: str | None = None
    ) -> DeliverableSetV1:
        """兼容仅消费成品集合的调用方，生命周期仍由外层 Graph 管理。"""
        result = await self.execute(submission, run_id=run_id)
        if result.deliverables is None:
            raise ValueError(result.error_code or "OPERATION_ALL_SPECIALISTS_FAILED")
        return result.deliverables

    async def execute(
        self, submission: ScenarioSubmission, *, run_id: str | None = None
    ) -> OperationExecution:
        """执行一次场景，所有暂态依赖和用量均按当前 Run 隔离。"""
        usage = OperationUsage()
        supervisor = self.supervisor_factory(run_id, usage)
        result = await ScenarioPackService(
            self.scenarios, supervisor, self.quality_gate
        ).run(submission)
        mapping = (
            {
                check_id: result.quality_report.report_id
                for check_id in self.scenarios.get(
                    submission.scenario_id, submission.manifest_semantic_version
                ).quality_check_ids
            }
            if result.quality_report
            else {}
        )
        if result.completion_status is CompletionStatus.CANCELLED:
            return OperationExecution(
                None,
                result.completion_status,
                usage.snapshot(),
                "OPERATION_CANCELLED",
                result,
                mapping,
            )
        if result.completion_status is CompletionStatus.WAITING_INPUT:
            return OperationExecution(
                None,
                result.completion_status,
                usage.snapshot(),
                "SCENARIO_INPUT_REQUIRED",
                result,
                mapping,
            )
        if (
            result.deliverable_bundle is None
            or result.completion_status is CompletionStatus.FAILED
        ):
            return OperationExecution(
                None,
                result.completion_status,
                usage.snapshot(),
                result.error_code or "OPERATION_ALL_SPECIALISTS_FAILED",
                result,
                mapping,
            )
        deliverables = self.assembler.assemble(
            [plain(item.payload) for item in result.deliverable_bundle.deliverables],
            missing_scope=result.missing_scope,
            degraded=result.completion_status is CompletionStatus.PARTIAL,
            quality_report=result.quality_report,
        )
        return OperationExecution(
            deliverables,
            result.completion_status,
            usage.snapshot(),
            scenario_result=result,
            quality_check_report_ids=mapping,
        )


__all__ = ["OperationAgent"]
