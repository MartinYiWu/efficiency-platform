"""父子预算账本的整数切分、消费和快照恢复测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.supervisor.budget import (
    BudgetLedger,
    BudgetUsage,
)
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject


def _parent() -> ExecutionBudget:
    return ExecutionBudget(10, 10, 100, 100, 100, 100)


def _request(value: int = 10) -> ExecutionBudget:
    return ExecutionBudget(value, value, value * 10, value * 10, value * 10, value * 10)


class BudgetLedgerTests(unittest.TestCase):
    def test_allocate_uses_integer_70_15_15_pools_and_stable_remainder(self) -> None:
        ledger = BudgetLedger.allocate(
            _parent(),
            (("b", _request()), ("a", _request()), ("c", _request())),
        )
        # 工作池为7，三个等权任务按 task_id 顺序得到 3、2、2。
        self.assertEqual(
            tuple(
                ledger.budget_for(task_id, _request()).max_iterations
                for task_id in ("a", "b", "c")
            ),
            (3, 2, 2),
        )
        self.assertEqual(ledger.pool("work").max_iterations, 7)
        self.assertEqual(ledger.pool("revision").max_iterations, 1)
        self.assertEqual(ledger.pool("aggregation").max_iterations, 2)

    def test_agent_cap_is_applied_field_by_field(self) -> None:
        ledger = BudgetLedger.allocate(_parent(), (("a", _request()),))
        cap = ExecutionBudget(2, 1, 3, 4, 5, 6)
        self.assertEqual(ledger.budget_for("a", cap), cap)

    def test_consume_rejects_any_dimension_overflow_without_partial_write(self) -> None:
        ledger = BudgetLedger.allocate(_parent(), (("a", _request()),))
        ledger.budget_for("a", _request())
        ledger.consume("a", BudgetUsage(iterations=1, input_tokens=1))
        before = ledger.consumed_total()
        with self.assertRaisesRegex(ValueError, "BUDGET_EXHAUSTED"):
            ledger.consume("a", BudgetUsage(iterations=9, input_tokens=100))
        self.assertEqual(ledger.consumed_total(), before)

    def test_release_unstarted_pool_can_be_reallocated(self) -> None:
        ledger = BudgetLedger.allocate(
            _parent(), (("a", _request()), ("b", _request()))
        )
        ledger.release_unstarted("b")
        self.assertGreaterEqual(ledger.budget_for("a", _request()).max_iterations, 7)

    def test_revision_reserve_is_bounded_and_consumed_budget_is_not_restored(
        self,
    ) -> None:
        ledger = BudgetLedger.allocate(
            _parent(), (("a", _request()), ("b", _request()))
        )
        ledger.budget_for("a", _request())
        ledger.consume("a", BudgetUsage(iterations=1, input_tokens=1))
        before = ledger.consumed_total()
        revision = ledger.reserve_revision("a")
        self.assertGreaterEqual(revision.max_iterations, 1)
        restored = BudgetLedger.restore(ledger.snapshot())
        self.assertEqual(restored.consumed_total(), before)
        self.assertLessEqual(
            restored.remaining_total().max_iterations,
            ledger.remaining_total().max_iterations,
        )

    def test_snapshot_is_immutable_json_object_and_restore_rejects_tampering(
        self,
    ) -> None:
        ledger = BudgetLedger.allocate(_parent(), (("a", _request()),))
        snapshot = ledger.snapshot()
        self.assertIsInstance(snapshot, JsonObject)
        with self.assertRaises((TypeError, ValueError)):
            BudgetLedger.restore(JsonObject((("contract_version", "budget-ledger/2"),)))


if __name__ == "__main__":
    unittest.main()
