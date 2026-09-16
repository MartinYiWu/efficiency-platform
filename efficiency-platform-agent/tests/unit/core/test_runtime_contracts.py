"""Run、Usage、事件及策略载荷的核心契约测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from efficiency_platform_agent.core.budget import BudgetCharge, BudgetGuard
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    RunRequest,
)
from efficiency_platform_agent.core.runtime import (
    RunFailure,
    RunRecord,
    StrategyPayload,
    UsageSnapshot,
)


def budget() -> ExecutionBudget:
    """构造测试预算。"""
    return ExecutionBudget(
        max_iterations=3,
        max_tool_calls=2,
        max_input_tokens=100,
        max_output_tokens=50,
        timeout_ms=1_000,
        max_cost_microunits=25,
    )


def record() -> RunRecord:
    """构造 CREATED Run。"""
    execution_budget = budget()
    return RunRecord(
        run_id="run-1",
        request=RunRequest("req-1", "tenant-1", "user-1", "问题"),
        status=RunStatus.CREATED,
        strategy=None,
        budget=execution_budget,
        budget_state=BudgetGuard().start(execution_budget, now_epoch_ms=1_000),
        usage=UsageSnapshot(estimated=True),
        version=1,
    )


def test_run_transition_increments_version_through_success_path() -> None:
    """CREATED→QUEUED→RUNNING→SUCCEEDED 版本依次为 1 至 3。"""
    current = record()
    current = current.transition(RunStatus.QUEUED)
    assert current.version == 2
    current = current.transition(RunStatus.RUNNING, strategy=StrategyMode.DIRECT)
    assert current.version == 3
    current = current.transition(
        RunStatus.SUCCEEDED, output=JsonObject((("content", "ok"),))
    )
    assert current.version == 4


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunStatus.CREATED, RunStatus.RUNNING),
        (RunStatus.WAITING_INPUT, RunStatus.SUCCEEDED),
        (RunStatus.SUCCEEDED, RunStatus.RUNNING),
    ],
)
def test_run_transition_rejects_illegal_paths(
    current: RunStatus, target: RunStatus
) -> None:
    """非法状态跳转必须失败关闭。"""
    source = record()
    if current is not RunStatus.CREATED:
        source = source.transition(RunStatus.QUEUED).transition(RunStatus.RUNNING)
        if current is RunStatus.WAITING_INPUT:
            source = source.transition(RunStatus.WAITING_INPUT)
        elif current is RunStatus.SUCCEEDED:
            source = source.transition(RunStatus.SUCCEEDED, output="ok")
    with pytest.raises(ValueError):
        source.transition(target, output="ok")


def test_run_transition_enforces_terminal_payload_invariants() -> None:
    """成功必须有输出，失败终态必须有错误，非终态不得携带最终值。"""
    source = record().transition(RunStatus.QUEUED).transition(RunStatus.RUNNING)
    with pytest.raises(ValueError):
        source.transition(RunStatus.SUCCEEDED)
    with pytest.raises(ValueError):
        source.transition(RunStatus.FAILED)
    with pytest.raises(ValueError):
        source.transition(RunStatus.WAITING_INPUT, output="leak")
    failure = RunFailure("E", "runtime", False, "安全错误")
    failed = source.transition(RunStatus.FAILED, failure=failure)
    assert failed.failure == failure
    with pytest.raises(ValueError):
        failed.transition(RunStatus.RUNNING)


@pytest.mark.parametrize(
    ("status", "output", "failure"),
    [
        (RunStatus.SUCCEEDED, None, None),
        (RunStatus.SUCCEEDED, "ok", RunFailure("E", "runtime", False, "安全错误")),
        (RunStatus.FAILED, None, None),
        (RunStatus.FAILED, "unexpected", RunFailure("E", "runtime", False, "安全错误")),
        (
            RunStatus.TIMED_OUT,
            "unexpected",
            RunFailure("E", "runtime", False, "安全错误"),
        ),
        (RunStatus.RUNNING, "unexpected", None),
        (RunStatus.RUNNING, None, RunFailure("E", "runtime", False, "安全错误")),
    ],
)
def test_run_record_rejects_invalid_terminal_payload_on_direct_construction(
    status: RunStatus,
    output: str | None,
    failure: RunFailure | None,
) -> None:
    """直接构造或恢复快照时也必须满足状态与最终载荷不变量。"""
    source = record()
    with pytest.raises(ValueError):
        RunRecord(
            run_id=source.run_id,
            request=source.request,
            status=status,
            strategy=source.strategy,
            budget=source.budget,
            budget_state=source.budget_state,
            usage=source.usage,
            version=source.version,
            output=output,
            failure=failure,
            checkpoint_id=source.checkpoint_id,
            degraded=source.degraded,
        )


def test_core_values_are_immutable_and_non_negative() -> None:
    """Usage 与策略载荷必须冻结且拒绝负计数。"""
    usage = UsageSnapshot(
        input_tokens=1, output_tokens=2, cost_microunits=3, estimated=True
    )
    with pytest.raises(FrozenInstanceError):
        usage.input_tokens = 2
    with pytest.raises(ValueError):
        UsageSnapshot(input_tokens=-1)
    with pytest.raises(ValueError):
        StrategyPayload("", JsonObject())
    payload = StrategyPayload("strategy.none/1", JsonObject((("x", (1, 2)),)))
    with pytest.raises(FrozenInstanceError):
        payload.data = JsonObject()


def test_budget_state_cannot_go_backwards_or_rewrite_deadline() -> None:
    """Run 转换不得倒退消费或替换原绝对 deadline。"""
    source = record().transition(RunStatus.QUEUED)
    state = source.budget_state
    with pytest.raises(ValueError):
        source.transition(
            RunStatus.RUNNING,
            budget_state=type(state)(
                BudgetCharge(iterations=-1),
                state.started_at_epoch_ms,
                state.deadline_epoch_ms,
            ),
        )
    with pytest.raises(ValueError):
        source.transition(
            RunStatus.RUNNING,
            budget_state=type(state)(
                state.consumed, state.started_at_epoch_ms, state.deadline_epoch_ms + 1
            ),
        )
