"""运营请求、任务与完整性契约测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.contracts.errors import (
    OperationDomainError,
    OperationErrorCode,
)
from efficiency_platform_agent.agents.operation.contracts.task import (
    AssumptionStatus,
    ConditionImportance,
    DeliverableKind,
    DeliverableRequirement,
    KeyCondition,
    OperationAssumption,
    OperationDomain,
    OperationGoal,
    OperationGoalKind,
    OperationIntent,
    OperationObject,
    OperationObjectKind,
    OperationRequest,
    OperationTaskSpec,
    SourceScope,
    validate_task_spec,
)
from efficiency_platform_agent.core.run import JsonObject, RunRequest


def _request(*, tenant_id: str = "tenant-a", user_id: str = "user-a") -> RunRequest:
    return RunRequest(
        request_id="request-a",
        tenant_id=tenant_id,
        user_id=user_id,
        input_text="制定运营方案",
    )


def _deliverable() -> DeliverableRequirement:
    return DeliverableRequirement(
        requirement_id="report",
        kind=DeliverableKind.REPORT,
        quantity=1,
        channel_ids=(),
        format_id="markdown",
        structure_id="report-v1",
        quality_check_ids=frozenset(),
    )


def _condition(
    condition_id: str,
    importance: ConditionImportance = ConditionImportance.OPTIONAL,
    value: JsonObject | None = None,
) -> KeyCondition:
    return KeyCondition(condition_id, condition_id, importance, value)


def _base_task(**overrides: object) -> OperationTaskSpec:
    values: dict[str, object] = {
        "contract_version": "operation-task/1",
        "task_id": "task-a",
        "tenant_id": "tenant-a",
        "user_id": "user-a",
        "session_id": "session-a",
        "parent_task_id": None,
        "operation_id": "operation-a",
        "intent": OperationIntent.RESEARCH,
        "domains": frozenset({OperationDomain.CONTENT}),
        "goals": (
            OperationGoal(
                "goal-a",
                OperationGoalKind.AWARENESS,
                None,
                "提升认知",
            ),
        ),
        "objects": (
            OperationObject(
                "object-a", OperationObjectKind.CONTENT, "已有文章", "asset-a"
            ),
        ),
        "key_conditions": (),
        "assumptions": (),
        "source_scopes": frozenset({SourceScope.USER_INPUT}),
        "deliverable_requirements": (_deliverable(),),
        "missing_critical_condition_ids": (),
        "requires_user_input": False,
    }
    values.update(overrides)
    return OperationTaskSpec(**values)  # type: ignore[arg-type]


class TaskContractTest(unittest.TestCase):
    """验证运营任务的不可变性、身份链和完整性规则。"""

    def test_task_spec_requires_waiting_input_for_missing_critical_brand_strategy(
        self,
    ) -> None:
        task = _base_task(
            intent=OperationIntent.PLAN,
            domains=frozenset({OperationDomain.BRAND}),
            goals=(),
            objects=(),
            key_conditions=(_condition("brand", ConditionImportance.CRITICAL),),
            missing_critical_condition_ids=("brand", "goal"),
            requires_user_input=True,
        )
        with self.assertRaises(OperationDomainError) as raised:
            validate_task_spec(task)
        self.assertEqual(
            raised.exception.detail.code,
            OperationErrorCode.OPERATION_INPUT_INCOMPLETE,
        )
        self.assertEqual(
            raised.exception.detail.missing_condition_ids, ("brand", "goal")
        )

    def test_task_spec_rejects_noncritical_gap_without_modifiable_assumption(
        self,
    ) -> None:
        task = _base_task(
            key_conditions=(_condition("tone"),),
            assumptions=(),
            missing_critical_condition_ids=(),
            requires_user_input=False,
        )
        with self.assertRaises(OperationDomainError):
            validate_task_spec(task)

    def test_operation_request_rejects_request_tenant_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            OperationRequest(
                contract_version="operation-request/1",
                request=_request(tenant_id="tenant-a"),
                operation_id="operation-a",
                session_id="session-a",
                parent_task_id=None,
                requested_domains=frozenset({OperationDomain.CONTENT}),
                requested_deliverables=(_deliverable(),),
            ).to_task_spec(
                task_id="task-a",
                tenant_id="tenant-b",
                user_id="user-a",
                intent=OperationIntent.RESEARCH,
                domains=frozenset({OperationDomain.CONTENT}),
                goals=(),
                objects=(),
                key_conditions=(),
                assumptions=(),
                source_scopes=frozenset({SourceScope.USER_INPUT}),
                missing_critical_condition_ids=(),
                requires_user_input=False,
            )

    def test_task_spec_preserves_session_parent_task_and_operation_identity(
        self,
    ) -> None:
        request = OperationRequest(
            contract_version="operation-request/1",
            request=_request(),
            operation_id="operation-a",
            session_id="session-a",
            parent_task_id="task-parent",
            requested_domains=frozenset({OperationDomain.CONTENT}),
            requested_deliverables=(_deliverable(),),
        )
        task = request.to_task_spec(
            task_id="task-child",
            tenant_id="tenant-a",
            user_id="user-a",
            intent=OperationIntent.REWRITE,
            domains=frozenset({OperationDomain.CONTENT}),
            goals=(),
            objects=(),
            key_conditions=(),
            assumptions=(),
            source_scopes=frozenset({SourceScope.USER_INPUT}),
            missing_critical_condition_ids=(),
            requires_user_input=False,
        )
        self.assertEqual(
            (task.session_id, task.parent_task_id, task.task_id, task.operation_id),
            ("session-a", "task-parent", "task-child", "operation-a"),
        )

    def test_stable_id_rule_matches_s1_for_single_character_and_edge_punctuation(
        self,
    ) -> None:
        self.assertEqual(_base_task(task_id="a").task_id, "a")
        for invalid_id in ("-a", "a-", ".a", "a_", "A"):
            with self.subTest(invalid_id=invalid_id), self.assertRaises(ValueError):
                _base_task(task_id=invalid_id)

    def test_noncritical_missing_condition_requires_modifiable_assumption(self) -> None:
        assumption = OperationAssumption(
            assumption_id="assumption-tone",
            condition_id="tone",
            value=JsonObject(),
            basis="用户未提供调性，采用默认中性表达",
            status=AssumptionStatus.PROPOSED,
            user_modifiable=True,
        )
        task = _base_task(
            key_conditions=(_condition("tone"),),
            assumptions=(assumption,),
        )
        validate_task_spec(task)


if __name__ == "__main__":
    unittest.main()
