"""有界多 Agent 波次调度的离线测试。"""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass
from types import SimpleNamespace

from efficiency_platform_agent.core.diagnostics import DiagnosticRecord
from efficiency_platform_agent.core.multi_agent import (
    BudgetUsage,
    TaskExecutionStatus,
)
from efficiency_platform_agent.strategies.multi_agent.scheduler import BoundedScheduler
from efficiency_platform_agent.strategies.multi_agent.state import (
    OperationSupervisorState,
)


def _state(ids: tuple[str, ...]) -> OperationSupervisorState:
    return {
        "run_id": "run-a",
        "tenant_id": "tenant-a",
        "user_id": "user-a",
        "strategy_payload_schema_version": "operation-strategy-payload/1",
        "strategy_payload": {"operation_request": {"text": "研究"}},
        "parent_deadline_epoch_ms": 9_999_999_999_999,
        "operation_request": None,
        "operation_task": None,
        "operation_context": None,
        "operation_plan": None,
        "plan_id": "plan-a",
        "plan_contract_version": "operation-plan/1",
        "plan_revision": 0,
        "task_graph": None,
        "task_statuses": {task_id: "ready" for task_id in ids},
        "attempts": {task_id: 0 for task_id in ids},
        "task_revisions": {task_id: 0 for task_id in ids},
        "fence_token": 0,
        "budget_ledger": {},
        "outcomes": {},
        "pending_input": None,
        "completion_status": None,
        "output": None,
        "error_code": None,
    }


@dataclass
class _Probe:
    active: int = 0
    max_active: int = 0


class _Plugin:
    def __init__(self, task_id: str, probe: _Probe, *, fail: bool = False) -> None:
        self.task_id, self.probe, self.fail = task_id, probe, fail

    async def run(self, task: object) -> object:
        self.probe.active += 1
        self.probe.max_active = max(self.probe.max_active, self.probe.active)
        await asyncio.sleep(0)
        self.probe.active -= 1
        if self.fail:
            raise RuntimeError("故意失败")
        return {"status": "succeeded", "usage": BudgetUsage(iterations=1)}


class _Selector:
    def rank(self, node: object) -> tuple[object, ...]:
        return (node,)


class _Factory:
    def __init__(self, probe: _Probe) -> None:
        self.probe = probe

    def create(self, agent_id: str) -> _Plugin:
        return _Plugin(agent_id, self.probe)


class _Dispatch:
    def build(self, node: object, selected: object, **kwargs: object) -> object:
        return node


class _Cancel:
    def __init__(self) -> None:
        self.event = asyncio.Event()

    async def wait_requested(self, run_id: str) -> None:
        await self.event.wait()

    async def is_requested(self, run_id: str) -> bool:
        return self.event.is_set()


class _Recorder:
    def __init__(self) -> None:
        self.records: list[DiagnosticRecord] = []

    def record(self, record: DiagnosticRecord) -> None:
        self.records.append(record)


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_wave_limits_parallelism_to_four_and_returns_only_first_wave(
        self,
    ) -> None:
        probe = _Probe()
        scheduler = BoundedScheduler(
            _Selector(), _Factory(probe), _Dispatch(), _Cancel()
        )
        result = await scheduler.run_wave(_state(tuple(f"task-{i}" for i in range(8))))
        self.assertEqual(probe.max_active, 4)
        self.assertEqual(len(result.outcomes), 4)
        self.assertTrue(
            all(
                item.status is TaskExecutionStatus.SUCCEEDED for item in result.outcomes
            ),
            result,
        )

    async def test_cancel_signal_wakes_blocked_specialist_immediately(self) -> None:
        cancel = _Cancel()
        started = asyncio.Event()
        stopped = asyncio.Event()

        class BlockingPlugin(_Plugin):
            async def run(self, task: object) -> object:
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    stopped.set()
                    raise

        class BlockingFactory(_Factory):
            def create(self, agent_id: str) -> BlockingPlugin:
                return BlockingPlugin(agent_id, self.probe)

        probe = _Probe()
        scheduler = BoundedScheduler(
            _Selector(), BlockingFactory(probe), _Dispatch(), cancel
        )
        running = asyncio.create_task(scheduler.run_wave(_state(("task-0",))))
        await asyncio.wait_for(started.wait(), timeout=1)
        cancel.event.set()
        result = await asyncio.wait_for(running, timeout=1)

        self.assertTrue(stopped.is_set())
        self.assertTrue(result.cancelled)
        self.assertEqual(result.outcomes[0].status, TaskExecutionStatus.CANCELLED)

    async def test_timeout_returns_failed_outcome_and_cleans_specialist(self) -> None:
        started = asyncio.Event()
        stopped = asyncio.Event()

        class SlowPlugin(_Plugin):
            async def run(self, task: object) -> object:
                started.set()
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    stopped.set()
                    raise

        class SlowFactory(_Factory):
            def create(self, agent_id: str) -> SlowPlugin:
                return SlowPlugin(agent_id, self.probe)

        probe = _Probe()
        state = _state(("task-0",))
        state["parent_deadline_epoch_ms"] = (
            int(asyncio.get_running_loop().time() * 1000) + 500
        )
        scheduler = BoundedScheduler(
            _Selector(),
            SlowFactory(probe),
            _Dispatch(),
            _Cancel(),
            clock=lambda: int(asyncio.get_running_loop().time() * 1000),
        )
        running = asyncio.create_task(scheduler.run_wave(state))
        await asyncio.wait_for(started.wait(), timeout=1)
        result = await asyncio.wait_for(running, timeout=1)

        self.assertTrue(stopped.is_set())
        self.assertEqual(result.outcomes[0].error_code, "TIMED_OUT")
        self.assertEqual(result.outcomes[0].status, TaskExecutionStatus.FAILED)

    async def test_timeout_records_safe_specialist_failure_diagnostic(self) -> None:
        class SlowPlugin(_Plugin):
            async def run(self, task: object) -> object:
                await asyncio.sleep(1)
                return {"status": "succeeded"}

        class SlowFactory(_Factory):
            def create(self, agent_id: str) -> SlowPlugin:
                return SlowPlugin(agent_id, self.probe)

        recorder = _Recorder()
        state = _state(("task-0",))
        state["parent_deadline_epoch_ms"] = (
            int(asyncio.get_running_loop().time() * 1000) + 20
        )
        scheduler = BoundedScheduler(
            _Selector(),
            SlowFactory(_Probe()),
            _Dispatch(),
            _Cancel(),
            clock=lambda: int(asyncio.get_running_loop().time() * 1000),
            diagnostic_recorder=recorder,
        )

        result = await scheduler.run_wave(state)

        self.assertEqual(result.outcomes[0].error_code, "TIMED_OUT")
        self.assertEqual(recorder.records[-1].event_name, "specialist_execution_failed")
        self.assertEqual(recorder.records[-1].error_code, "TIMED_OUT")
        self.assertEqual(recorder.records[-1].stage, "specialist.run")

    async def test_research_node_timeout_maps_to_research_unavailable(self) -> None:
        """研究节点超时必须输出稳定业务错误，不能暴露通用调度超时。"""

        class SlowPlugin(_Plugin):
            async def run(self, task: object) -> object:
                await asyncio.sleep(1)
                return {"status": "succeeded"}

        class SlowFactory(_Factory):
            def create(self, agent_id: str) -> SlowPlugin:
                return SlowPlugin(agent_id, self.probe)

        node = SimpleNamespace(
            task_id="research",
            task_type="operation.research",
            depends_on=(),
        )
        state = _state(("research",))
        state["parent_deadline_epoch_ms"] = (
            int(asyncio.get_running_loop().time() * 1000) + 20
        )
        scheduler = BoundedScheduler(
            _Selector(),
            SlowFactory(_Probe()),
            _Dispatch(),
            _Cancel(),
            graph=SimpleNamespace(tasks=(node,)),
            clock=lambda: int(asyncio.get_running_loop().time() * 1000),
        )

        result = await scheduler.run_wave(state)

        self.assertEqual(result.outcomes[0].error_code, "RESEARCH_UNAVAILABLE")
        self.assertEqual(result.outcomes[0].status, TaskExecutionStatus.FAILED)

    async def test_failed_candidate_switches_to_next_candidate(self) -> None:
        probe = _Probe()

        class TwoCandidates:
            def rank(self, node: object) -> tuple[str, ...]:
                return ("first", "second")

        class SwitchingFactory:
            def create(self, agent_id: str) -> _Plugin:
                if agent_id == "first":
                    raise RuntimeError("首个候选不可用")
                return _Plugin(agent_id, probe)

        scheduler = BoundedScheduler(
            TwoCandidates(), SwitchingFactory(), _Dispatch(), _Cancel()
        )
        result = await scheduler.run_wave(_state(("task-0",)))

        self.assertEqual(result.outcomes[0].status, TaskExecutionStatus.SUCCEEDED)
        self.assertEqual(result.outcomes[0].agent_id, "second")


if __name__ == "__main__":
    unittest.main()
