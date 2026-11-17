"""任务内去重、进展及跨层尝试额度只使用本机合成操作。"""

import asyncio

import pytest

from efficiency_platform_agent.core.paid_budget import PaidBudgetError


async def test_success_and_inflight_are_shared_without_cross_task_cache():
    from efficiency_platform_agent.core.execution_control import RunControl

    calls = []

    async def work():
        calls.append(True)
        await asyncio.sleep(0)
        return "结果"

    control = RunControl()
    assert (
        await asyncio.gather(*(control.execute("same", work) for _ in range(8)))
        == ["结果"] * 8
    )
    assert calls == [True]
    assert await control.execute("same", work) == "结果"
    assert await RunControl().execute("same", work) == "结果"
    assert len(calls) == 2


async def test_three_completed_replays_stop_but_distinct_evidence_is_progress():
    from efficiency_platform_agent.core.execution_control import RunControl

    control = RunControl()

    async def work():
        return "相同判断"

    for key in ("doc1", "doc2", "doc3", "doc4"):
        await control.execute(key, work)
    for _ in range(2):
        await control.execute("doc4", work)
    with pytest.raises(PaidBudgetError) as caught:
        await control.execute("doc4", work)
    assert caught.value.code == "AGENT_NO_PROGRESS"
    with pytest.raises(PaidBudgetError):
        await control.execute("new", work)


async def test_shared_waiter_cancel_does_not_cancel_work_but_task_stop_does():
    from efficiency_platform_agent.core.execution_control import RunControl

    control = RunControl()
    entered = asyncio.Event()
    released = asyncio.Event()

    async def work():
        entered.set()
        await released.wait()
        return 1

    first = asyncio.create_task(control.execute("same", work))
    await entered.wait()
    second = asyncio.create_task(control.execute("same", work))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    released.set()
    assert await second == 1
    released.clear()
    pending = asyncio.create_task(control.execute("different", work))
    await asyncio.sleep(0)
    await control.close()
    with pytest.raises((asyncio.CancelledError, PaidBudgetError)):
        await pending
    assert not control.pending


async def test_attempts_share_operation_and_stop_other_operations():
    from efficiency_platform_agent.core.execution_control import (
        RunControl,
        consume_http_attempt,
    )

    control = RunControl()
    sent = []

    async def work():
        for _ in range(4):
            consume_http_attempt()
            sent.append(True)

    with pytest.raises(PaidBudgetError) as caught:
        await control.execute("same", work)
    assert caught.value.code == "AGENT_OPERATION_ATTEMPTS_EXHAUSTED"
    assert len(sent) == 3
    with pytest.raises(PaidBudgetError):
        await control.execute("other", work)


async def test_reentry_cannot_reset_attempts_after_failure():
    from efficiency_platform_agent.core.execution_control import (
        RunControl,
        consume_http_attempt,
    )

    control = RunControl()

    async def work():
        consume_http_attempt()
        raise ValueError("固定错误")

    with pytest.raises(ValueError):
        await control.execute("same", work)
    with pytest.raises(PaidBudgetError):
        await control.execute("same", work)
