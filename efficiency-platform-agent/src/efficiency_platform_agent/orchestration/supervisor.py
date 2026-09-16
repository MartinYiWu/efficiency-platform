"""S6 到 S4 的编排适配器：复用编译、注册选择、预算与有界调度。"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import Any

from efficiency_platform_agent.agents.factory import AgentFactory
from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    DeliverableBundle,
    OperationQualityReport,
    QualityStatus,
)
from efficiency_platform_agent.agents.operation.quality.evidence_gate import (
    EvidenceGate,
    EvidenceGatePolicy,
)
from efficiency_platform_agent.agents.operation.scenarios.contracts import (
    ScenarioExecutionResult,
    ScenarioSupervisorRequest,
)
from efficiency_platform_agent.agents.operation.specialists.model_backed import (
    evidence_citations,
    freeze,
    plain,
)
from efficiency_platform_agent.agents.operation.specialists.research import (
    ResearchInsightAgent,
)
from efficiency_platform_agent.agents.operation.supervisor.aggregation import (
    ResultAggregator,
)
from efficiency_platform_agent.agents.operation.supervisor.budget import BudgetLedger
from efficiency_platform_agent.agents.operation.supervisor.dispatch import (
    DispatchBuilder,
    SpecialistResultDecoder,
)
from efficiency_platform_agent.agents.operation.supervisor.planning import (
    OperationPlanCompiler,
)
from efficiency_platform_agent.agents.operation.supervisor.selection import (
    SpecialistSelector,
)
from efficiency_platform_agent.agents.registry import AgentRegistry
from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchProviderPort,
    ResearchRequest,
    ResearchResult,
    ResearchStatus,
)
from efficiency_platform_agent.core.diagnostics import (
    DiagnosticRecorderPort,
    NoopDiagnosticRecorder,
)
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.multi_agent import (
    CompletionStatus,
    SupervisorLimits,
    TaskExecutionStatus,
)
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject, RunResult
from efficiency_platform_agent.strategies.multi_agent.scheduler import BoundedScheduler
from efficiency_platform_agent.strategies.multi_agent.state import (
    OperationSupervisorState,
)


class _ScenarioDispatch:
    """每次运行独立裁剪任务输入，不向子任务泄露整个父态。"""

    def __init__(self, delegate, request, results):
        self.delegate = delegate
        self.request = request
        self.results = results

    def build(self, node, selected, **kwargs):
        request = self.request
        platform = (
            node.task_id.replace("-", "_")
            if node.task_type == "operation.channel_content"
            else ("research" if node.task_type == "operation.research" else "general")
        )
        inputs = [
            plain(item.payload)
            for task_id, envelope in self.results.items()
            if task_id in node.depends_on and envelope.deliverable_bundle
            for item in envelope.deliverable_bundle.deliverables
        ]
        value = freeze(
            {
                "platform": platform,
                "tenant_id": request.task_spec.tenant_id,
                "goal": request.request.request.input_text,
                "task_id": request.task_spec.task_id,
                "plan_id": request.operation_plan.plan_id,
                "deliverable_id": node.expected_deliverable_ids[0],
                "citations": evidence_citations(request.evidence_pack),
                "input_deliverables": inputs,
                "research": node.task_type == "operation.research"
                or bool(getattr(request.task_spec, "requires_research", False)),
            }
        )
        kwargs["input_data"] = value
        return self.delegate.build(node, selected, **kwargs)


def compile_runtime_plan(plan):
    """无损编码版本化质量 ID，保留原始 ID 以供审计追溯。"""
    execution_plan = replace(
        plan,
        steps=tuple(
            replace(
                step,
                quality_check_ids=frozenset(
                    "q-" + check.encode("utf-8").hex()
                    for check in step.quality_check_ids
                ),
            )
            for step in plan.steps
        ),
    )
    graph = OperationPlanCompiler(SupervisorLimits()).compile(execution_plan)
    originals = {step.step_id: step.quality_check_ids for step in plan.steps}
    return replace(
        graph,
        tasks=tuple(
            replace(
                node,
                context_view=JsonObject(
                    (
                        *node.context_view.items,
                        (
                            "original_quality_check_ids",
                            tuple(sorted(originals[node.task_id])),
                        ),
                    )
                ),
            )
            for node in graph.tasks
        ),
    )


class ScenarioSupervisorAdapter:
    """受控执行单个场景；该对象是图节点依赖，不拥有 Run 生命周期。"""

    _RESEARCH_BUDGET = ExecutionBudget(3, 1, 4_000, 8_000, 240_000, 0)

    def __init__(
        self,
        registry: AgentRegistry,
        *,
        budget: ExecutionBudget,
        cancellation: Any = None,
        run_id: str | None = None,
        diagnostic_recorder: DiagnosticRecorderPort | None = None,
        research_provider: ResearchProviderPort | None = None,
        usage: Any = None,
    ):
        self.registry = registry
        self.budget = budget
        self.cancellation = cancellation
        self.run_id = run_id
        self.diagnostic_recorder = diagnostic_recorder or NoopDiagnosticRecorder()
        self.research_provider = research_provider
        self.usage = usage

    async def _prepare_research(
        self, request: ScenarioSupervisorRequest, graph: Any
    ) -> ScenarioSupervisorRequest:
        """在平台专家运行前建立一次证据包，研究失败时安全关闭。"""

        if not getattr(request.task_spec, "requires_research", False):
            return request
        # 研究场景已有专用研究 Specialist；由其产出交付物和证据，避免重复联网。
        if any(node.task_type == "operation.research" for node in graph.tasks):
            return request
        provider = self.research_provider
        if not isinstance(provider, ResearchProviderPort):
            raise ValueError("RESEARCH_UNAVAILABLE")  # noqa: TRY004
        task_spec = request.task_spec
        research_request = ResearchRequest(
            "research-request/1",
            f"research-{request.submission_id}",
            task_spec.task_id,
            task_spec.tenant_id,
            request.request.request.input_text,
            None,
            1,
            ("goal",),
            "research-result/1",
            self._RESEARCH_BUDGET.max_output_tokens,
        )
        try:
            result = await asyncio.wait_for(
                provider.research(research_request),
                timeout=self._RESEARCH_BUDGET.timeout_ms / 1000,
            )
        except TimeoutError as error:
            raise ValueError("RESEARCH_UNAVAILABLE") from error
        except Exception as error:
            # Provider 异常不能穿透到用户，统一收敛为稳定研究错误码。
            raise ValueError("RESEARCH_UNAVAILABLE") from error
        if not isinstance(result, ResearchResult):
            raise ValueError("RESEARCH_UNAVAILABLE")  # noqa: TRY004
        record_snapshot = getattr(self.usage, "record_snapshot", None)
        if callable(record_snapshot):
            record_snapshot(result.usage)
        if (
            result.request_id != research_request.request_id
            or result.task_id != research_request.task_id
            or result.tenant_id != research_request.tenant_id
        ):
            raise ValueError("EVIDENCE_INVALID")
        if result.status is not ResearchStatus.SUCCEEDED or not result.observations:
            # 研究供应商的细分失败码只留在内部诊断；对用户统一暴露稳定的研究不可用错误。
            raise ValueError("RESEARCH_UNAVAILABLE")
        pack = ResearchInsightAgent._evidence_pack(
            task_spec.task_id, result.observations
        )
        decision = EvidenceGate().evaluate(
            pack,
            frozenset({"goal"}),
            EvidenceGatePolicy("research-v1", 1, 1, True, True),
        )
        if not decision.accepted:
            raise ValueError(
                decision.reason_codes[0] if decision.reason_codes else "EVIDENCE_INVALID"
            )
        return replace(request, evidence_pack=pack)

    async def execute_scenario(
        self, request: ScenarioSupervisorRequest
    ) -> ScenarioExecutionResult:
        """逐波运行独立专家，并对可用成品明确保留部分成功。"""
        plan = request.operation_plan
        graph = compile_runtime_plan(plan)
        # 多平台模板包含三个平台；当前请求显式指定平台时仅执行对应节点。
        channels = {
            channel
            for requirement in request.request.requested_deliverables
            for channel in requirement.channel_ids
        }
        if channels and plan.source_template_id == "multi_platform_content-template":
            supported = {node.task_id.replace("-", "_") for node in graph.tasks}
            if not channels.issubset(supported):
                raise ValueError("OPERATION_PLATFORM_UNSUPPORTED")
            nodes = tuple(
                node
                for node in graph.tasks
                if node.task_id.replace("-", "_") in channels
            )
            if not nodes:
                raise ValueError("OPERATION_PLATFORM_UNSUPPORTED")
            graph = replace(
                graph,
                tasks=nodes,
                topological_order=tuple(node.task_id for node in nodes),
            )
        request = await self._prepare_research(request, graph)
        ledger = BudgetLedger.allocate(
            self.budget,
            tuple((node.task_id, node.requested_budget) for node in graph.tasks),
        )
        factory = AgentFactory(self.registry)
        envelopes: dict[str, Any] = {}
        scheduler = BoundedScheduler(
            SpecialistSelector(self.registry),
            factory,
            _ScenarioDispatch(DispatchBuilder(factory, ledger), request, envelopes),
            ledger=ledger,
            cancellation=self.cancellation,
            graph=graph,
            diagnostic_recorder=self.diagnostic_recorder,
        )
        run_id = self.run_id or request.submission_id
        state: OperationSupervisorState = {
            "run_id": run_id,
            "tenant_id": request.task_spec.tenant_id,
            "user_id": request.task_spec.user_id,
            "strategy_payload_schema_version": "operation-strategy-payload/1",
            "strategy_payload": {},
            "parent_deadline_epoch_ms": int(time.time() * 1000)
            + self.budget.timeout_ms,
            "operation_request": None,
            "operation_task": None,
            "operation_context": None,
            "operation_plan": None,
            "plan_id": graph.plan_id,
            "plan_contract_version": graph.plan_contract_version,
            "plan_revision": 0,
            "task_graph": None,
            "task_statuses": {
                node.task_id: "ready" if not node.depends_on else "pending"
                for node in graph.tasks
            },
            "attempts": {},
            "task_revisions": {},
            "fence_token": 0,
            "budget_ledger": {},
            "outcomes": {},
            "pending_input": None,
            "completion_status": None,
            "output": None,
            "error_code": None,
        }
        outcomes: dict[str, Any] = {}
        cancelled = False
        for _ in range(len(graph.tasks)):
            wave = await scheduler.run_wave(state)
            if wave.cancelled:
                cancelled = True
                break
            if not wave.outcomes:
                break
            for outcome in wave.outcomes:
                if outcome.status is TaskExecutionStatus.SUCCEEDED:
                    try:
                        envelope = SpecialistResultDecoder().decode(
                            RunResult(
                                run_id,
                                RunStatus.SUCCEEDED,
                                StrategyMode.MULTI_AGENT,
                                outcome.result,
                            )
                        )
                        if envelope.task_id != outcome.task_id:
                            raise ValueError("SPECIALIST_TASK_MISMATCH")
                        envelopes[outcome.task_id] = envelope
                    except ValueError:
                        outcome = replace(
                            outcome,
                            status=TaskExecutionStatus.FAILED,
                            result=None,
                            error_code="OUTPUT_SCHEMA_INVALID",
                            completed_scope=(),
                            missing_scope=(outcome.task_id,),
                        )
                outcomes[outcome.task_id] = outcome
                state["task_statuses"][outcome.task_id] = outcome.status.value
            for node in graph.tasks:
                if state["task_statuses"][node.task_id] == "pending" and all(
                    state["task_statuses"][dependency] == "succeeded"
                    for dependency in node.depends_on
                ):
                    state["task_statuses"][node.task_id] = "ready"
        aggregated = ResultAggregator().aggregate(
            graph, tuple(outcomes.values()), tuple(envelopes.values())
        )
        scenario_id = (plan.source_template_id or "").removesuffix("-template")
        warnings = set(aggregated.warnings)
        # 输入模板的 required 表示范围要求；有成品时由场景层显式报告部分交付。
        status = (
            CompletionStatus.CANCELLED if cancelled else aggregated.completion_status
        )
        if not cancelled and aggregated.deliverables and aggregated.missing_scope:
            status = CompletionStatus.PARTIAL
            warnings.add("SPECIALIST_PARTIAL_FAILURE")
        reports = aggregated.quality_reports
        quality_report = None
        if reports and not cancelled:
            checks = tuple(check for report in reports for check in report.checks)
            final = (
                QualityStatus.FAILED
                if any(
                    report.final_status is QualityStatus.FAILED for report in reports
                )
                else QualityStatus.WARNING
                if any(
                    report.final_status
                    in {QualityStatus.WARNING, QualityStatus.UNKNOWN}
                    for report in reports
                )
                else QualityStatus.PASSED
            )
            quality_report = OperationQualityReport(
                "operation-quality-report/1",
                f"quality-{plan.plan_id}",
                request.task_spec.task_id,
                tuple(item.deliverable_id for item in aggregated.deliverables),
                checks,
                final,
                max(report.revision_count for report in reports),
            )
        bundle = (
            DeliverableBundle(
                "deliverable-bundle/1",
                f"{plan.plan_id}.bundle",
                request.task_spec.task_id,
                plan.plan_id,
                aggregated.deliverables,
                request.evidence_pack.pack_id if request.evidence_pack else None,
                tuple(report.report_id for report in reports)
                + ((quality_report.report_id,) if quality_report else ()),
                frozenset(),
            )
            if aggregated.deliverables and not cancelled
            else None
        )
        error_code = (
            "RESEARCH_UNAVAILABLE"
            if any(
                failure.endswith(":RESEARCH_UNAVAILABLE")
                for failure in aggregated.failures
            )
            else "OPERATION_ALL_SPECIALISTS_FAILED"
            if status is CompletionStatus.FAILED
            else None
        )
        return ScenarioExecutionResult(
            scenario_id,
            plan.source_template_version or "1.0.0",
            status,
            bundle,
            quality_report,
            (),
            aggregated.completed_scope,
            aggregated.missing_scope,
            frozenset(warnings),
            error_code,
        )
