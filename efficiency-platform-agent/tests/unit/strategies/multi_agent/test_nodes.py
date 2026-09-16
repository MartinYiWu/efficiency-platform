from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from efficiency_platform_agent.agents.operation.contracts.evidence import EvidencePack
from efficiency_platform_agent.agents.operation.contracts.planning import OperationPlan
from efficiency_platform_agent.agents.operation.contracts.profiles import (
    OperationContext,
)
from efficiency_platform_agent.agents.operation.contracts.task import (
    OperationRequest,
    OperationTaskSpec,
)
from efficiency_platform_agent.contracts.operation_strategy import (
    OperationStrategyPayloadAdapter,
)
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.multi_agent import (
    BudgetUsage,
    TaskExecutionStatus,
    TaskOutcome,
)
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject, RunRequest
from efficiency_platform_agent.strategies.multi_agent.nodes import (
    SupervisorDependencies,
    aggregate_node,
    assemble_node,
    build_operation_context_node,
    build_plan_node,
    compile_plan_node,
    decode_operation_request_node,
    normalize_intent_node,
    reconcile_wave_node,
    schedule_wave_node,
)
from efficiency_platform_agent.strategies.multi_agent.routing import (
    route_after_reconcile,
)


class OperationSupervisorNodeTests(unittest.TestCase):
    def test_payload_accepts_only_operation_request(self):
        adapter = OperationStrategyPayloadAdapter()
        payload = JsonObject((("operation_request", JsonObject()),))
        self.assertEqual(
            adapter.adapt(adapter.schema_version, payload).schema_version,
            adapter.schema_version,
        )

    def test_payload_rejects_precomputed_state(self):
        adapter = OperationStrategyPayloadAdapter()
        payload = JsonObject((("operation_plan", JsonObject()),))
        with self.assertRaisesRegex(ValueError, "PRECOMPUTED_STATE_FORBIDDEN"):
            adapter.adapt(adapter.schema_version, payload)

    def test_plain_json_payload_is_decoded_after_checkpoint_normalization(self):
        state = {
            "strategy_payload": {
                "operation_request": {
                    "request": {
                        "request_id": "request-plain",
                        "tenant_id": "tenant-a",
                        "user_id": "user-a",
                        "input_text": "研究运营主题",
                    },
                    "operation_id": "operation-plain",
                }
            }
        }

        decoded = decode_operation_request_node(state)

        self.assertIn("operation_request", decoded)

    def test_routing_is_framework_neutral(self):
        self.assertEqual(
            route_after_reconcile({"task_statuses": {"a": "succeeded"}}), "aggregate"
        )

    def test_cancelled_wave_sets_cancel_requested_for_terminal_routing(self):
        class Scheduler:
            async def run_wave(self, _state):
                return SimpleNamespace(cancelled=True, outcomes=(), event_intents=())

        deps = SupervisorDependencies(
            None,
            None,
            None,
            scheduler=Scheduler(),
        )
        patch = asyncio.run(
            schedule_wave_node(
                {
                    "run_id": "run-cancelled",
                    "task_statuses": {"task-1": "ready"},
                },
                deps,
            )
        )

        self.assertTrue(patch["cancel_requested"])

    def test_cancel_requested_state_is_monotonic(self):
        class Scheduler:
            async def run_wave(self, _state):
                return SimpleNamespace(cancelled=False, outcomes=(), event_intents=())

        deps = SupervisorDependencies(None, None, None, scheduler=Scheduler())
        patch = asyncio.run(
            schedule_wave_node(
                {
                    "run_id": "run-cancelled",
                    "cancel_requested": True,
                    "task_statuses": {"task-1": "ready"},
                },
                deps,
            )
        )

        self.assertTrue(patch["cancel_requested"])

    def test_s3_ports_and_fake_wave_are_called_once(self):
        request = OperationRequest(
            "operation-request/1",
            RunRequest("req-1", "tenant-1", "user-1", "写文案"),
            "op-1",
            None,
            None,
            frozenset(),
            (),
        )
        task = object.__new__(OperationTaskSpec)
        for name, value in {
            "contract_version": "operation-task/1",
            "task_id": "task-1",
            "tenant_id": "tenant-1",
            "user_id": "user-1",
            "session_id": None,
            "parent_task_id": None,
            "operation_id": "op-1",
            "intent": "create",
            "domains": frozenset(),
            "goals": (),
            "objects": (),
            "key_conditions": (),
            "assumptions": (),
            "source_scopes": frozenset(),
            "deliverable_requirements": (),
            "missing_critical_condition_ids": (),
            "requires_user_input": False,
        }.items():
            object.__setattr__(task, name, value)
        plan = OperationPlan(
            "operation-plan/1",
            "plan-1",
            "task-1",
            StrategyMode.MULTI_AGENT,
            None,
            None,
            (),
            (),
            ExecutionBudget(1, 0, 0, 0, 1_000, 0),
            frozenset({"complete"}),
        )
        outcome = TaskOutcome(
            "task-1",
            "agent-1",
            TaskExecutionStatus.SUCCEEDED,
            JsonObject((("content", "ok"),)),
            None,
            ("task-1",),
            (),
            BudgetUsage(),
            1,
            0,
            0,
        )

        class Port:
            def __init__(self, value):
                self.value, self.calls = value, 0

            def normalize(self, _):
                self.calls += 1
                return self.value

            def build_plan(self, *_):
                self.calls += 1
                return self.value

            def assemble(self, *_):
                self.calls += 1
                return JsonObject((("content", "done"),))

        class Scheduler:
            async def run_wave(self, _):
                return SimpleNamespace(outcomes=(outcome,), event_intents=())

        class Aggregator:
            def aggregate(self, *_):
                return SimpleNamespace(
                    completion_status=SimpleNamespace(value="complete"),
                    missing_scope=(),
                    evidence_pack=EvidencePack(
                        "evidence-pack/1", "pack-1", "task-1", (), ()
                    ),
                )

        intent, planning, assembly = Port(task), Port(plan), Port(None)
        deps = SupervisorDependencies(
            intent,
            planning,
            assembly,
            context_builder=lambda task: OperationContext(
                "operation-context/1",
                f"context-{task.task_id}",
                task.tenant_id,
                task.task_id,
                (),
                frozenset(),
            ),
            plan_compiler=lambda _: SimpleNamespace(),
            scheduler=Scheduler(),
            aggregator=Aggregator(),
        )
        state = {
            "run_id": "run-1",
            "strategy_payload": {"operation_request": request},
            "task_statuses": {"task-1": "ready"},
            "request_id": "req-1",
            "plan_revision": 0,
            "fence_token": 0,
        }
        decode_operation_request_node(state, deps)
        normalize_intent_node(state, deps)
        build_operation_context_node(state, deps)
        build_plan_node(state, deps)
        compile_plan_node(state, deps)
        asyncio.run(schedule_wave_node(state, deps))
        reconcile_wave_node(state, deps)
        aggregate_node(state, deps)
        assemble_node(state, deps)
        self.assertEqual((intent.calls, planning.calls, assembly.calls), (1, 1, 1))


if __name__ == "__main__":
    unittest.main()
