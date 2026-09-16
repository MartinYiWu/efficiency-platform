"""验证 S2 假端口与运营领域契约之间的字段完整性。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.contracts import (
    DeliverableKind,
    DeliverableRequirement,
    EvidencePack,
    OperationContext,
    OperationRequest,
    SourceScope,
)
from efficiency_platform_agent.core.run import JsonObject, RunRequest
from tests.support.s2_operation_fakes import (
    FakeS2OperationAssemblyPort,
    FakeS2OperationIntentPort,
    FakeS2OperationPlanningPort,
)


def _request(
    *,
    tenant_id: str = "tenant-a",
    user_id: str = "user-a",
    session_id: str | None = "session-a",
    parent_task_id: str | None = "parent-task-a",
) -> OperationRequest:
    """构造仅用于契约测试的声明性运营请求。"""
    request = RunRequest(
        request_id="request-a",
        tenant_id=tenant_id,
        user_id=user_id,
        input_text="研究运营主题并形成结构化交付物",
    )
    requirement = DeliverableRequirement(
        requirement_id="report",
        kind=DeliverableKind.REPORT,
        quantity=1,
        channel_ids=("internal",),
        format_id="markdown",
        structure_id="report",
        quality_check_ids=frozenset({"completeness"}),
    )
    return OperationRequest(
        contract_version="operation-request/1",
        request=request,
        operation_id="operation-a",
        session_id=session_id,
        parent_task_id=parent_task_id,
        requested_domains=frozenset(),
        requested_deliverables=(requirement,),
    )


def _context(task_id: str, tenant_id: str) -> OperationContext:
    """构造不携带 Profile 的最小任务上下文。"""
    return OperationContext(
        contract_version="operation-context/1",
        context_id="context-a",
        tenant_id=tenant_id,
        task_id=task_id,
        profile_references=(),
        source_scope_ids=frozenset({SourceScope.USER_INPUT}),
    )


def _empty_evidence(task_id: str) -> EvidencePack:
    """构造不宣称事实已核验的空证据包。"""
    return EvidencePack(
        contract_version="evidence-pack/1",
        pack_id="evidence-a",
        task_id=task_id,
        records=(),
        supports=(),
    )


class OperationDomainContractTests(unittest.TestCase):
    """确认 S2、S3 与后续 S4/S5 可消费的字段不在边界丢失。"""

    def test_fake_s2_contract_chain_preserves_identity_and_references(self) -> None:
        request = _request()
        task = FakeS2OperationIntentPort().normalize(request)
        context = _context(task.task_id, task.tenant_id)
        plan = FakeS2OperationPlanningPort().build_plan(task, context)
        bundle = FakeS2OperationAssemblyPort().assemble(
            task, plan, _empty_evidence(task.task_id)
        )

        self.assertEqual((task.tenant_id, context.tenant_id), ("tenant-a", "tenant-a"))
        self.assertEqual(
            (task.session_id, task.parent_task_id), ("session-a", "parent-task-a")
        )
        self.assertEqual(task.operation_id, request.operation_id)
        self.assertEqual(bundle.task_id, task.task_id)
        self.assertEqual(bundle.plan_id, plan.plan_id)

    def test_s4_selection_contract_is_complete_after_fake_plan_creation(self) -> None:
        request = _request()
        task = FakeS2OperationIntentPort().normalize(request)
        plan = FakeS2OperationPlanningPort().build_plan(
            task, _context(task.task_id, task.tenant_id)
        )

        self.assertTrue(plan.steps)
        for step in plan.steps:
            self.assertTrue(step.task_type)
            self.assertTrue(step.input_schema_version)
            self.assertTrue(step.output_schema_version)
            self.assertIsNotNone(step.required_capabilities)
            self.assertIsInstance(step.required_permissions, frozenset)
            self.assertIsInstance(step.allowed_tools, frozenset)
            self.assertIsInstance(step.required, bool)
            self.assertIsNotNone(step.failure_behavior)

    def test_evidence_and_deliverable_handoff_preserves_traceability(self) -> None:
        request = _request()
        task = FakeS2OperationIntentPort().normalize(request)
        plan = FakeS2OperationPlanningPort().build_plan(
            task, _context(task.task_id, task.tenant_id)
        )
        bundle = FakeS2OperationAssemblyPort().assemble(
            task, plan, _empty_evidence(task.task_id)
        )

        deliverable = bundle.deliverables[0]
        self.assertEqual(deliverable.plan_id, plan.plan_id)
        self.assertTrue(deliverable.generation_process.plan_step_ids)
        self.assertTrue(
            all(
                step_id in {step.step_id for step in plan.steps}
                for step_id in deliverable.generation_process.plan_step_ids
            )
        )
        self.assertEqual(deliverable.payload, JsonObject())
        self.assertEqual(
            (deliverable.prompt_bundle_id is None),
            (deliverable.prompt_bundle_version is None),
        )


__all__ = ["OperationDomainContractTests"]
