"""S4 Supervisor 代表性离线验收；不连接真实基础设施。"""

from __future__ import annotations

import asyncio
import time
import unittest
from types import SimpleNamespace

from efficiency_platform_agent.agents.factory import AgentFactory
from efficiency_platform_agent.agents.operation.supervisor.aggregation import (
    ResultAggregator,
)
from efficiency_platform_agent.agents.operation.supervisor.budget import BudgetLedger
from efficiency_platform_agent.agents.operation.supervisor.dispatch import (
    DispatchBuilder,
)
from efficiency_platform_agent.agents.operation.supervisor.planning import (
    OperationPlanCompiler,
)
from efficiency_platform_agent.agents.operation.supervisor.selection import (
    SpecialistSelector,
)
from efficiency_platform_agent.contracts.operation_resume import OperationResumeValueV1
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.multi_agent import (
    BudgetUsage,
    SupervisorLimits,
    TaskExecutionStatus,
    TaskGraph,
    TaskOutcome,
)
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject
from efficiency_platform_agent.harness.operation_supervisor_factory import (
    register_operation_supervisor,
)
from efficiency_platform_agent.orchestration.registry import GraphRegistry
from efficiency_platform_agent.orchestration.runtime import GraphRuntime
from efficiency_platform_agent.routing.strategy_router import StrategySelection
from efficiency_platform_agent.strategies.multi_agent.nodes import (
    SupervisorDependencies,
    decode_operation_request_node,
)
from efficiency_platform_agent.strategies.multi_agent.scheduler import BoundedScheduler
from tests.support.s2_operation_fakes import (
    FakeS2OperationAssemblyPort,
    FakeS2OperationIntentPort,
    FakeS2OperationPlanningPort,
    build_context,
)
from tests.support.supervisor_fakes import (
    build_specialist_spec,
    build_task_node,
    register_specialists,
)


def _state(task_id: str, graph: TaskGraph) -> dict[str, object]:
    """构造只含可序列化基础值的 Supervisor 状态。"""
    return {
        "run_id": "run-acceptance",
        "tenant_id": "tenant-a",
        "user_id": "user-a",
        "strategy_payload_schema_version": "operation-strategy-payload/1",
        "strategy_payload": {"operation_request": {}},
        "parent_deadline_epoch_ms": int(time.time() * 1000) + 60_000,
        "operation_request": None,
        "operation_task": None,
        "operation_context": None,
        "operation_plan": None,
        "plan_id": graph.plan_id,
        "plan_contract_version": graph.plan_contract_version,
        "plan_revision": graph.plan_revision,
        "task_graph": None,
        "task_statuses": {task_id: "ready"},
        "attempts": {task_id: 0},
        "task_revisions": {task_id: 0},
        "fence_token": 0,
        "budget_ledger": {},
        "outcomes": {},
        "pending_input": None,
        "completion_status": None,
        "output": None,
        "error_code": None,
    }


class OperationSupervisorAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    """验证选择、预算、调度和预计算状态拒绝的代表性闭环。"""

    async def test_synthetic_specialist_completes_one_wave_without_external_io(
        self,
    ) -> None:
        node = build_task_node()
        graph = TaskGraph(
            "plan-acceptance", "operation-plan/1", 0, (node,), (node.task_id,)
        )
        spec = build_specialist_spec("specialist_a")
        registry = register_specialists((spec,))
        ledger = BudgetLedger.allocate(
            ExecutionBudget(10, 10, 1_000, 1_000, 30_000, 100),
            ((node.task_id, node.requested_budget),),
        )
        factory = AgentFactory(registry)
        scheduler = BoundedScheduler(
            SpecialistSelector(registry),
            factory,
            DispatchBuilder(
                factory,
                ledger,
            ),
            ledger=ledger,
            graph=graph,
        )

        wave = await scheduler.run_wave(_state(node.task_id, graph))

        self.assertEqual(len(wave.outcomes), 1)
        self.assertEqual(wave.outcomes[0].status.value, "succeeded")
        self.assertEqual(wave.dispatched_task_ids, (node.task_id,))

    def test_precomputed_plan_payload_is_rejected_before_supervisor_nodes(self) -> None:
        state = {
            "strategy_payload": {
                "operation_request": JsonObject(
                    (
                        (
                            "request",
                            JsonObject(
                                (
                                    ("request_id", "request-a"),
                                    ("tenant_id", "tenant-a"),
                                    ("user_id", "user-a"),
                                    ("input_text", "研究运营主题"),
                                )
                            ),
                        ),
                        ("operation_id", "operation-a"),
                        ("plan", JsonObject()),
                    )
                )
            }
        }
        with self.assertRaisesRegex(ValueError, "operation_request"):
            decode_operation_request_node(state)

    def test_s4_plan_compiler_keeps_single_graph_runtime_boundary(self) -> None:
        self.assertTrue(hasattr(OperationPlanCompiler(SupervisorLimits()), "compile"))
        self.assertEqual(StrategyMode.MULTI_AGENT.value, "multi_agent")

    async def test_graph_builder_runs_s3_chain_and_returns_terminal_output(
        self,
    ) -> None:
        """验证 Supervisor 图实际串起请求、计划、聚合和 assembly。"""

        request = JsonObject(
            (
                (
                    "operation_request",
                    JsonObject(
                        (
                            (
                                "request",
                                JsonObject(
                                    (
                                        ("request_id", "request-graph"),
                                        ("tenant_id", "tenant-a"),
                                        ("user_id", "user-a"),
                                        ("input_text", "研究运营主题"),
                                    )
                                ),
                            ),
                            ("operation_id", "operation-graph"),
                        )
                    ),
                ),
            )
        )

        class Scheduler:
            async def run_wave(self, _state: object) -> object:
                return SimpleNamespace(
                    outcomes=(
                        TaskOutcome(
                            "research",
                            "specialist-a",
                            TaskExecutionStatus.SUCCEEDED,
                            JsonObject((("content", "离线研究结果"),)),
                            None,
                            ("research",),
                            (),
                            BudgetUsage(iterations=1),
                            1,
                            0,
                            0,
                        ),
                    ),
                    event_intents=(),
                )

        dependencies = SupervisorDependencies(
            FakeS2OperationIntentPort(),
            FakeS2OperationPlanningPort(),
            FakeS2OperationAssemblyPort(),
            context_builder=build_context,
            plan_compiler=OperationPlanCompiler(SupervisorLimits()),
            scheduler=Scheduler(),
            aggregator=ResultAggregator(),
        )
        registry = GraphRegistry()
        register_operation_supervisor(registry, dependencies)
        runtime = GraphRuntime(registry)
        result = await runtime.execute(
            StrategySelection(StrategyMode.MULTI_AGENT, "s4.test", "test"),
            {
                "run_id": "run-graph",
                "request_id": "request-graph",
                "strategy_payload": request,
                "parent_deadline_epoch_ms": int(time.time() * 1000) + 60_000,
                "task_statuses": {},
                "plan_revision": 0,
                "fence_token": 0,
            },
        )
        self.assertEqual(result.next_status.value, "succeeded")
        self.assertIsInstance(result.output, JsonObject)

    async def test_graph_builder_cancellation_reaches_cancelled_terminal_state(
        self,
    ) -> None:
        """验证波次取消会沿图路由进入 CANCELLED，而不是重复调度。"""

        class CancelledScheduler:
            async def run_wave(self, _state: object) -> object:
                return SimpleNamespace(outcomes=(), event_intents=(), cancelled=True)

        request = JsonObject(
            (
                (
                    "operation_request",
                    JsonObject(
                        (
                            (
                                "request",
                                JsonObject(
                                    (
                                        ("request_id", "request-cancel"),
                                        ("tenant_id", "tenant-a"),
                                        ("user_id", "user-a"),
                                        ("input_text", "研究运营主题"),
                                    )
                                ),
                            ),
                            ("operation_id", "operation-cancel"),
                        )
                    ),
                ),
            )
        )
        dependencies = SupervisorDependencies(
            FakeS2OperationIntentPort(),
            FakeS2OperationPlanningPort(),
            FakeS2OperationAssemblyPort(),
            context_builder=build_context,
            plan_compiler=OperationPlanCompiler(SupervisorLimits()),
            scheduler=CancelledScheduler(),
            aggregator=ResultAggregator(),
        )
        registry = GraphRegistry()
        register_operation_supervisor(registry, dependencies)
        runtime = GraphRuntime(registry)

        result = await runtime.execute(
            StrategySelection(StrategyMode.MULTI_AGENT, "s4.cancel", "test"),
            {
                "run_id": "run-cancel",
                "request_id": "request-cancel",
                "strategy_payload": request,
                "parent_deadline_epoch_ms": int(time.time() * 1000) + 60_000,
                "task_statuses": {},
                "plan_revision": 0,
                "fence_token": 0,
            },
        )

        self.assertEqual(result.next_status, RunStatus.CANCELLED)
        self.assertIsNone(result.output)

    async def test_graph_runtime_resume_reuses_waiting_checkpoint(self) -> None:
        """验证等待输入后恢复仍使用原 Run 和检查点继续执行。"""

        class SuccessfulScheduler:
            async def run_wave(self, _state: object) -> object:
                return SimpleNamespace(
                    outcomes=(
                        TaskOutcome(
                            "research",
                            "specialist-a",
                            TaskExecutionStatus.SUCCEEDED,
                            JsonObject((("content", "离线研究结果"),)),
                            None,
                            ("research",),
                            (),
                            BudgetUsage(iterations=1),
                            1,
                            0,
                            0,
                        ),
                    ),
                    event_intents=(),
                    cancelled=False,
                )

        class WaitingThenCompleteAggregator:
            def __init__(self) -> None:
                self.calls = 0

            def aggregate(self, _graph: object, _outcomes: object) -> object:
                self.calls += 1
                waiting = self.calls == 1
                return SimpleNamespace(
                    completion_status=SimpleNamespace(
                        value="waiting_input" if waiting else "complete"
                    ),
                    missing_scope=("topic",) if waiting else (),
                    evidence_pack=None,
                )

        request = JsonObject(
            (
                (
                    "operation_request",
                    JsonObject(
                        (
                            (
                                "request",
                                JsonObject(
                                    (
                                        ("request_id", "request-resume"),
                                        ("tenant_id", "tenant-a"),
                                        ("user_id", "user-a"),
                                        ("input_text", "研究运营主题"),
                                    )
                                ),
                            ),
                            ("operation_id", "operation-resume"),
                        )
                    ),
                ),
            )
        )
        aggregator = WaitingThenCompleteAggregator()
        dependencies = SupervisorDependencies(
            FakeS2OperationIntentPort(),
            FakeS2OperationPlanningPort(),
            FakeS2OperationAssemblyPort(),
            context_builder=build_context,
            plan_compiler=OperationPlanCompiler(SupervisorLimits()),
            scheduler=SuccessfulScheduler(),
            aggregator=aggregator,
        )
        registry = GraphRegistry()
        register_operation_supervisor(registry, dependencies)
        runtime = GraphRuntime(registry)
        selection = StrategySelection(StrategyMode.MULTI_AGENT, "s4.resume", "test")
        initial_state = {
            "run_id": "run-resume",
            "request_id": "request-resume",
            "strategy_payload": request,
            "parent_deadline_epoch_ms": int(time.time() * 1000) + 60_000,
            "task_statuses": {},
            "plan_revision": 0,
            "fence_token": 0,
        }

        first = await runtime.execute(selection, initial_state)
        self.assertEqual(first.next_status, RunStatus.WAITING_INPUT)
        self.assertEqual(aggregator.calls, 1)
        checkpoint = first.checkpoint
        resume_value = OperationResumeValueV1(
            request_id="request-resume",
            plan_revision=0,
            supplemental={"topic": "补充主题"},
            fence_token=0,
        ).to_json()

        resumed = await asyncio.wait_for(
            runtime.resume(
                selection,
                "run-resume",
                checkpoint.checkpoint_id,
                resume_value,
            ),
            timeout=2,
        )

        self.assertEqual(resumed.next_status, RunStatus.SUCCEEDED)
        self.assertEqual(aggregator.calls, 2)


__all__ = ["OperationSupervisorAcceptanceTests"]
