"""仅供 S3 离线契约测试使用的确定性 S2 假端口。"""

from __future__ import annotations

from efficiency_platform_agent.agents.operation.contracts import (
    DeliverableBundle,
    DeliverableRequirement,
    EvidencePack,
    FailureBehavior,
    GenerationProcessReference,
    OperationContext,
    OperationDeliverable,
    OperationDomain,
    OperationGoal,
    OperationGoalKind,
    OperationIntent,
    OperationObject,
    OperationObjectKind,
    OperationPlan,
    OperationPlanStep,
    OperationRequest,
    OperationTaskSpec,
    SourceScope,
)
from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    DeliverableKind as OutputDeliverableKind,
)
from efficiency_platform_agent.agents.operation.contracts.task import (
    DeliverableKind as RequirementDeliverableKind,
)
from efficiency_platform_agent.core.agent import CapabilityRequirement
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject


def _budget() -> ExecutionBudget:
    """构造离线测试预算，不代表生产默认值。"""
    return ExecutionBudget(4, 4, 400, 400, 2_000, 100)


def build_operation_request(
    *,
    tenant_id: str = "tenant-a",
    user_id: str = "user-a",
    session_id: str | None = "session.test",
    parent_task_id: str | None = None,
) -> OperationRequest:
    """构造供三个假端口共同消费的最小请求。"""
    from efficiency_platform_agent.core.run import RunRequest

    return OperationRequest(
        "operation-request/1",
        RunRequest("request.test", tenant_id, user_id, "研究运营主题"),
        "operation.test",
        session_id,
        parent_task_id,
        frozenset({OperationDomain.CONTENT}),
        (
            DeliverableRequirement(
                "report",
                RequirementDeliverableKind.REPORT,
                1,
                ("web",),
                "markdown",
                "report",
                frozenset({"quality.source"}),
            ),
        ),
    )


def build_context(task: OperationTaskSpec) -> OperationContext:
    """构造与任务身份一致的最小上下文。"""
    return OperationContext(
        "operation-context/1",
        "context.test",
        task.tenant_id,
        task.task_id,
        (),
        frozenset({SourceScope.USER_INPUT}),
    )


def build_empty_evidence_pack(task_id: str) -> EvidencePack:
    """构造不含外部事实的空证据包。"""
    return EvidencePack("evidence-pack/1", "evidence.test", task_id, (), ())


class FakeS2OperationIntentPort:
    """把测试请求确定性归一化为运营任务，不调用模型。"""

    def normalize(self, request: OperationRequest) -> OperationTaskSpec:
        return request.to_task_spec(
            task_id="operation-task.test",
            tenant_id=request.request.tenant_id,
            user_id=request.request.user_id,
            intent=OperationIntent.RESEARCH,
            domains=request.requested_domains or frozenset({OperationDomain.CONTENT}),
            goals=(
                OperationGoal(
                    "goal.test",
                    OperationGoalKind.AWARENESS,
                    None,
                    "形成离线研究骨架",
                ),
            ),
            objects=(
                OperationObject(
                    "object.test",
                    OperationObjectKind.CONTENT,
                    "运营主题",
                    None,
                ),
            ),
            key_conditions=(),
            assumptions=(),
            source_scopes=frozenset({SourceScope.USER_INPUT}),
            missing_critical_condition_ids=(),
            requires_user_input=False,
        )


class FakeS2OperationPlanningPort:
    """为离线契约生成一个稳定的单步骤计划。"""

    def build_plan(
        self, task: OperationTaskSpec, context: OperationContext
    ) -> OperationPlan:
        budget = _budget()
        step = OperationPlanStep(
            "research",
            "operation.research",
            (),
            CapabilityRequirement(all_of=frozenset({"operation.research"})),
            "operation-research-input/1",
            "operation-research-output/1",
            (),
            context,
            frozenset({"public.search"}),
            frozenset({"public.read"}),
            budget,
            ("report",),
            frozenset({"quality.source"}),
            True,
            FailureBehavior.FAIL,
        )
        return OperationPlan(
            "operation-plan/1",
            "operation-plan.test",
            task.task_id,
            StrategyMode.WORKFLOW,
            None,
            None,
            ("all_required_steps_succeeded",),
            (step,),
            budget,
            frozenset({"stop_on_failure"}),
        )


class FakeS2OperationAssemblyPort:
    """将离线计划和证据组装为声明性交付物，不保存文件。"""

    def assemble(
        self,
        task: OperationTaskSpec,
        plan: OperationPlan,
        evidence: EvidencePack,
    ) -> DeliverableBundle:
        deliverable = OperationDeliverable(
            "operation-deliverable/1",
            "operation-deliverable.test",
            OutputDeliverableKind.REPORT,
            "1.0.0",
            "运营研究交付物",
            ("object.test",),
            ("web",),
            None,
            JsonObject(),
            frozenset(),
            frozenset(),
            frozenset(),
            (),
            GenerationProcessReference(
                "operation-generation.test", "1.0.0", (plan.steps[0].step_id,), ()
            ),
            None,
            None,
            plan.plan_id,
            None,
            None,
        )
        return DeliverableBundle(
            "deliverable-bundle/1",
            "operation-bundle.test",
            task.task_id,
            plan.plan_id,
            (deliverable,),
            evidence.pack_id,
            (),
            frozenset(),
        )


__all__ = [
    "FakeS2OperationAssemblyPort",
    "FakeS2OperationIntentPort",
    "FakeS2OperationPlanningPort",
    "build_context",
    "build_empty_evidence_pack",
    "build_operation_request",
]
