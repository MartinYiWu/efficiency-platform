"""多 Agent Supervisor 状态的可序列化边界测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.strategies.multi_agent.state import (
    OperationSupervisorState,
    validate_supervisor_state,
)


def _state(**changes: object) -> OperationSupervisorState:
    value: OperationSupervisorState = {
        "run_id": "run-a",
        "tenant_id": "tenant-a",
        "user_id": "user-a",
        "strategy_payload_schema_version": "operation-strategy-payload/1",
        "strategy_payload": {"operation_request": {"text": "研究"}},
        "parent_deadline_epoch_ms": 9_999_999_999,
        "operation_request": None,
        "operation_task": None,
        "operation_context": None,
        "operation_plan": None,
        "plan_id": None,
        "plan_contract_version": None,
        "plan_revision": 0,
        "task_graph": None,
        "task_statuses": {},
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
    value.update(changes)  # type: ignore[arg-type]
    return value


class SupervisorStateTests(unittest.TestCase):
    def test_initial_state_accepts_json_primitives_only(self) -> None:
        validate_supervisor_state(_state())

    def test_rejects_agent_task_exception_and_mutable_runtime_objects(self) -> None:
        for bad in (object(), ValueError("x")):
            with self.assertRaisesRegex(ValueError, "STATE_NOT_SERIALIZABLE"):
                validate_supervisor_state(_state(strategy_payload={"bad": bad}))

    def test_rejects_precomputed_runtime_fields_in_strategy_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "PRECOMPUTED_STATE_FORBIDDEN"):
            validate_supervisor_state(_state(strategy_payload={"plan": {"x": 1}}))

    def test_rejects_tuple_and_non_string_task_status_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "STATE_NOT_SERIALIZABLE"):
            validate_supervisor_state(_state(strategy_payload={"items": (1, 2)}))
        with self.assertRaisesRegex(ValueError, "STATE_NOT_SERIALIZABLE"):
            validate_supervisor_state(_state(task_statuses={1: "ready"}))


if __name__ == "__main__":
    unittest.main()
