from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


class MultiAgentCoreContractsTest(unittest.TestCase):
    def setUp(self) -> None:
        from efficiency_platform_agent.core.agent import CapabilityRequirement
        from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject

        self.CapabilityRequirement = CapabilityRequirement
        self.ExecutionBudget = ExecutionBudget
        self.JsonObject = JsonObject

    def budget(self, **overrides):
        values = {
            "max_iterations": 5,
            "max_tool_calls": 3,
            "max_input_tokens": 100,
            "max_output_tokens": 100,
            "timeout_ms": 1_000,
            "max_cost_microunits": 10,
        }
        values.update(overrides)
        return self.ExecutionBudget(**values)

    def capability(self):
        return self.CapabilityRequirement(all_of=frozenset({"research.read"}))

    def node(self, task_id: str = "task-a", **overrides):
        from efficiency_platform_agent.core.multi_agent import TaskFailureMode, TaskNode

        values = {
            "task_id": task_id,
            "task_type": "research",
            "capability_requirement": self.capability(),
            "input_schema_version": "operation-input/1",
            "output_schema_version": "operation-output/1",
            "depends_on": (),
            "required": True,
            "failure_mode": TaskFailureMode.FAIL_PLAN,
            "input_reference_ids": (),
            "context_view": self.JsonObject(),
            "allowed_tools": frozenset(),
            "required_permissions": frozenset(),
            "requested_budget": self.budget(),
            "expected_deliverable_ids": (),
            "quality_check_ids": frozenset(),
        }
        values.update(overrides)
        return TaskNode(**values)

    def supervisor_task(self):
        from efficiency_platform_agent.core.run import SupervisorTask

        return SupervisorTask(
            task_id="task-a",
            parent_run_id="run-1",
            target_agent="specialist-a",
            input_data=self.JsonObject((("query", "x"),)),
            context_view=self.JsonObject(),
            allowed_tools=frozenset(),
            budget=self.budget(),
        )

    def test_platform_limits_are_fixed_and_cannot_be_expanded(self) -> None:
        from efficiency_platform_agent.core.multi_agent import SupervisorLimits

        limits = SupervisorLimits()
        self.assertEqual(limits.max_delegation_depth, 1)
        self.assertEqual(limits.max_dag_depth, 8)
        self.assertEqual(limits.max_task_count, 16)
        self.assertEqual(limits.max_parallel_tasks, 4)
        self.assertEqual(limits.max_plan_revisions, 2)
        self.assertEqual(limits.max_task_revisions, 2)
        restricted = limits.restrict(max_parallel_tasks=2, max_task_count=8)
        self.assertEqual(restricted.max_parallel_tasks, 2)
        self.assertEqual(restricted.max_task_count, 8)
        with self.assertRaises(ValueError):
            limits.restrict(max_parallel_tasks=5)
        with self.assertRaises(ValueError):
            limits.restrict(max_task_count=0)

    def test_core_types_are_frozen_slots_dataclasses(self) -> None:
        from efficiency_platform_agent.core.multi_agent import (
            BudgetUsage,
            CompletionStatus,
            TaskExecutionStatus,
            TaskFailureMode,
        )

        values = [
            BudgetUsage(),
            self.node(),
        ]
        self.assertEqual(TaskExecutionStatus.PENDING.value, "pending")
        self.assertEqual(TaskFailureMode.RETRY_ONCE.value, "retry_once")
        self.assertEqual(CompletionStatus.PARTIAL.value, "partial")
        for value in values:
            self.assertTrue(is_dataclass(value))
            self.assertTrue(hasattr(type(value), "__slots__"))
            self.assertTrue(type(value).__dataclass_params__.frozen)
        with self.assertRaises(FrozenInstanceError):
            values[0].iterations = 1

    def test_task_node_requires_immutable_sequences_and_valid_budget(self) -> None:
        with self.assertRaises(TypeError):
            self.node(depends_on=["task-b"])
        with self.assertRaises(TypeError):
            self.node(input_reference_ids=["input-1"])
        with self.assertRaises(ValueError):
            self.node(depends_on=("task-a",))
        with self.assertRaises(ValueError):
            self.node(required=False)

    def test_task_graph_rejects_empty_or_invalid_revision_and_keeps_order(self) -> None:
        from efficiency_platform_agent.core.multi_agent import TaskGraph

        with self.assertRaises(ValueError):
            TaskGraph("plan-1", "operation-plan/1", 0, (), ())
        with self.assertRaises(TypeError):
            TaskGraph("plan-1", "operation-plan/1", 0, [self.node()], ("task-a",))
        with self.assertRaises(ValueError):
            TaskGraph(
                "plan-1",
                "operation-plan/1",
                3,
                (self.node(),),
                ("task-a",),
            )
        graph = TaskGraph("plan-1", "operation-plan/1", 0, (self.node(),), ("task-a",))
        self.assertEqual(graph.topological_order, ("task-a",))

    def test_dispatch_wraps_s1_supervisor_task_without_mutating_it(self) -> None:
        from efficiency_platform_agent.core.multi_agent import TaskDispatch

        dispatch = TaskDispatch(
            task=self.supervisor_task(),
            capability_ids=frozenset({"research.read"}),
            attempt=1,
            revision=0,
            fence_token=0,
            parent_deadline_epoch_ms=2_000,
        )
        self.assertEqual(dispatch.task.task_id, "task-a")
        self.assertEqual(dispatch.capability_ids, frozenset({"research.read"}))
        with self.assertRaises(ValueError):
            TaskDispatch(
                task=self.supervisor_task(),
                capability_ids=frozenset(),
                attempt=0,
                revision=0,
                fence_token=0,
                parent_deadline_epoch_ms=2_000,
            )

    def test_task_outcome_validates_status_result_and_usage(self) -> None:
        from efficiency_platform_agent.core.multi_agent import (
            BudgetUsage,
            TaskExecutionStatus,
            TaskOutcome,
        )

        outcome = TaskOutcome(
            task_id="task-a",
            agent_id="specialist-a",
            status=TaskExecutionStatus.SUCCEEDED,
            result=self.JsonObject((("content", "ok"),)),
            error_code=None,
            completed_scope=("task-a",),
            missing_scope=(),
            trusted_usage=BudgetUsage(output_tokens=2),
            attempt=1,
            revision=0,
            fence_token=0,
        )
        self.assertEqual(outcome.trusted_usage.output_tokens, 2)
        with self.assertRaises(ValueError):
            TaskOutcome(
                task_id="task-a",
                agent_id="specialist-a",
                status=TaskExecutionStatus.SUCCEEDED,
                result=None,
                error_code=None,
                completed_scope=(),
                missing_scope=(),
                trusted_usage=BudgetUsage(),
                attempt=1,
                revision=0,
                fence_token=0,
            )


if __name__ == "__main__":
    unittest.main()
