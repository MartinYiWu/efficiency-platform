"""研究洞察 Specialist：固定调用研究端口并经过 Evidence Gate。"""

from __future__ import annotations

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    DeliverableBundle,
    DeliverableKind,
    GenerationProcessReference,
    OperationDeliverable,
)
from efficiency_platform_agent.agents.operation.contracts.evidence import (
    ConclusionSupport,
    EvidencePack,
    EvidenceRecord,
)
from efficiency_platform_agent.agents.operation.quality.evidence_gate import (
    EvidenceGate,
    EvidenceGatePolicy,
)
from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchObservation,
    ResearchProviderPort,
    ResearchRequest,
    ResearchStatus,
)
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.multi_agent import BudgetUsage
from efficiency_platform_agent.core.run import JsonObject, RunResult, SupervisorTask

from ..definition import OperationSpecialistCapabilityId
from ._base import OperationSpecialistBase
from .contracts import SpecialistExecutionResult
from .runtime import decode_specialist_task, encode_specialist_result


class ResearchInsightAgent(OperationSpecialistBase):
    """将结构化研究观察转换为带证据关联的研究交付物。"""

    def __init__(
        self,
        provider: ResearchProviderPort,
        *,
        gate: EvidenceGate | None = None,
        policy: EvidenceGatePolicy | None = None,
    ) -> None:
        super().__init__(
            agent_id="operation.research.insight",
            capability_id=OperationSpecialistCapabilityId.RESEARCH_INSIGHT.value,
            task_type="operation.research",
            prompt_bundle_id="operation.research.insight/1",
            quality_policy_id="operation-evidence-quality/1",
            output_title="运营研究洞察",
            output_label="research_insight",
            output_kind=DeliverableKind.REPORT,
            strategy=StrategyMode.WORKFLOW,
            allowed_tools=frozenset({"synthetic_research"}),
            permissions=frozenset({"synthetic.read"}),
            max_iterations=3,
            max_tool_calls=1,
            max_input_tokens=4_000,
            max_output_tokens=8_000,
            timeout_ms=240_000,
        )
        if not isinstance(provider, ResearchProviderPort):
            raise TypeError("provider必须实现ResearchProviderPort")
        self._provider = provider
        self._gate = gate or EvidenceGate()
        self._policy = policy or EvidenceGatePolicy("research-v1", 1, 1, True, True)

    async def run(self, task: SupervisorTask) -> RunResult:
        """执行一次研究端口调用并在 Evidence Gate 失败时关闭。"""

        try:
            execution_input = decode_specialist_task(task)
            operation_task = execution_input.operation_task
            goals = tuple(
                getattr(goal, "goal_id", "goal") for goal in operation_task.goals
            )
            expected = goals or ("goal",)
            request = ResearchRequest(
                "research-request/1",
                f"research-{task.task_id}",
                task.task_id,
                execution_input.tenant_id,
                "；".join(
                    getattr(goal, "description", "运营研究")
                    for goal in operation_task.goals
                )
                or "运营研究",
                None,
                self._policy.minimum_valid_source_count,
                expected,
                "research-result/1",
            )
            result = await self._provider.research(request)
            if result.status is ResearchStatus.FAILED:
                return encode_specialist_result(
                    self._failure(
                        task.task_id, "RESEARCH_UNAVAILABLE"
                    ),
                    task.parent_run_id,
                )
            if (
                result.request_id != request.request_id
                or result.task_id != task.task_id
                or result.tenant_id != execution_input.tenant_id
            ):
                return encode_specialist_result(
                    self._failure(task.task_id, "EVIDENCE_INVALID"), task.parent_run_id
                )
            pack = self._evidence_pack(task.task_id, result.observations)
            decision = self._gate.evaluate(pack, frozenset(expected), self._policy)
            if not decision.accepted:
                return encode_specialist_result(
                    self._failure(
                        task.task_id,
                        decision.reason_codes[0]
                        if decision.reason_codes
                        else "EVIDENCE_INVALID",
                        pack,
                    ),
                    task.parent_run_id,
                )
            bundle = self._bundle(task.task_id, pack)
            success = SpecialistExecutionResult(
                "operation-specialist-result/1",
                task.task_id,
                (self.spec.agent_id,),
                (),
                bundle,
                pack,
                None,
                (),
                result.warnings,
                None,
                None,
                None,
                BudgetUsage(iterations=1),
            )
            return encode_specialist_result(success, task.parent_run_id)
        except (TypeError, ValueError):
            return encode_specialist_result(
                self._failure(task.task_id, "RESEARCH_UNAVAILABLE"), task.parent_run_id
            )
        except Exception:  # noqa: BLE001  # 研究供应商异常统一脱敏收敛
            # 研究供应商的网络、协议或解析异常不得穿透到用户层。
            return encode_specialist_result(
                self._failure(task.task_id, "RESEARCH_UNAVAILABLE"), task.parent_run_id
            )

    @staticmethod
    def _failure(
        task_id: str, code: str, pack: EvidencePack | None = None
    ) -> SpecialistExecutionResult:
        """构造不泄露 Provider 原始响应的失败结果。"""

        return SpecialistExecutionResult(
            "operation-specialist-result/1",
            task_id,
            (),
            (task_id,),
            None,
            pack,
            None,
            (),
            (),
            code,
            None,
            None,
            BudgetUsage(),
        )

    @staticmethod
    def _evidence_pack(
        task_id: str, observations: tuple[ResearchObservation, ...]
    ) -> EvidencePack:
        records = tuple(
            EvidenceRecord(
                observation.observation_id.replace("observation", "evidence"),
                observation.title,
                observation.publisher,
                observation.source_url,
                observation.published_at_epoch_ms,
                observation.retrieved_at_epoch_ms,
                observation.source_scope,
                observation.supported_conclusion_ids,
                observation.within_time_window,
                observation.duplicate_status,
                observation.quality_status,
            )
            for observation in observations
        )
        supports = tuple(
            ConclusionSupport(
                conclusion_id,
                frozenset(
                    record.evidence_id
                    for record in records
                    if conclusion_id in record.supported_conclusion_ids
                ),
            )
            for conclusion_id in sorted(
                {item for record in records for item in record.supported_conclusion_ids}
            )
        )
        return EvidencePack(
            "evidence-pack/1",
            f"research-evidence-{task_id}",
            task_id,
            records,
            supports,
        )

    @staticmethod
    def _bundle(task_id: str, pack: EvidencePack) -> DeliverableBundle:
        deliverable = OperationDeliverable(
            "operation-deliverable/1",
            f"research-report-{task_id}",
            DeliverableKind.REPORT,
            "1.0.0",
            "运营研究洞察",
            (task_id,),
            (),
            None,
            JsonObject((("evidence_count", len(pack.records)),)),
            frozenset(record.evidence_id for record in pack.records),
            frozenset(),
            frozenset(),
            (),
            GenerationProcessReference(
                f"research-process-{task_id}", "operation-research/1", (), ()
            ),
            "operation-research-insight",
            "1",
            f"plan-{task_id}",
            None,
            None,
        )
        return DeliverableBundle(
            "deliverable-bundle/1",
            f"research-bundle-{task_id}",
            task_id,
            f"plan-{task_id}",
            (deliverable,),
            pack.pack_id,
            (),
            frozenset(),
        )


__all__ = ["ResearchInsightAgent"]
