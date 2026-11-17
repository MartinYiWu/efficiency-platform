"""冲突检查不能重试致命错误、重复证据或创建无界排队工作。"""

import asyncio
from uuid import uuid4

import pytest
from test_evidence_assembly import group_fixture

from efficiency_platform_agent.agents.customer_service.conflict_screen import (
    screen_conflicts,
)
from efficiency_platform_agent.agents.customer_service.model_gateway import (
    StructuredModelError,
)
from efficiency_platform_agent.core.paid_budget import PaidBudgetError


def sources(count):
    _, initial = group_fixture()
    parents = tuple(
        initial[0].model_copy(update={"parent_id": uuid4(), "document_id": uuid4()})
        for _ in range(count)
    )
    members = {
        (p.knowledge_base_id, p.document_id, p.document_version_id, p.index_release_id)
        for p in parents
    }
    return parents, members


@pytest.mark.parametrize("batch", [False, True])
async def test_fatal_provider_error_is_not_retried_or_swallowed(batch):
    parents, members = sources(2)
    calls = []

    class Gateway:
        async def complete(self, *args):
            calls.append(True)
            raise StructuredModelError("PROVIDER_AUTH_FAILED", "鉴权失败")

    with pytest.raises(StructuredModelError):
        await screen_conflicts(
            parents,
            question="问题",
            gateway=Gateway(),
            members=members,
            stage_bound=True,
            batch_enabled=batch,
        )
    assert len(calls) == 1


async def test_workload_refused_before_any_provider_call():
    parents, members = sources(20)
    calls = []

    class Gateway:
        async def complete(self, *args):
            calls.append(True)
            raise AssertionError("不得发送")

    with pytest.raises(PaidBudgetError) as caught:
        await screen_conflicts(
            parents,
            question="问题",
            gateway=Gateway(),
            members=members,
            stage_bound=True,
        )
    assert caught.value.code == "AGENT_WORK_LIMIT_EXCEEDED"
    assert not calls


async def test_fatal_error_cancels_workers_and_prevents_new_queued_work():
    parents, members = sources(6)
    calls = []
    running = set()

    class Gateway:
        async def complete(self, *args):
            index = len(calls)
            calls.append(index)
            running.add(index)
            try:
                if index == 0:
                    await asyncio.sleep(0)
                    raise PaidBudgetError("BUDGET_STOPPED", "已停止")
                await asyncio.Event().wait()
            finally:
                running.remove(index)

    with pytest.raises(PaidBudgetError):
        await screen_conflicts(
            parents,
            question="问题",
            gateway=Gateway(),
            members=members,
            stage_bound=True,
        )
    assert len(calls) <= 8
    assert not running


@pytest.mark.parametrize("batch", [False, True])
async def test_duplicate_parents_do_not_create_duplicate_checks(batch):
    parents, members = sources(2)
    calls = []

    class Gateway:
        async def complete(self, stage, value, output_type):
            calls.append(value)
            left, right = value["evidence"]
            return output_type.model_validate(
                {
                    "pairs": [
                        {
                            "left_parent_id": left["parent_id"],
                            "right_parent_id": right["parent_id"],
                            "same_scope": False,
                            "verdict": "NO_CONFLICT",
                            "left_quote": left["content"],
                            "right_quote": right["content"],
                            "reason": "合成核验",
                        }
                    ]
                }
            )

    result = await screen_conflicts(
        parents + parents,
        question="问题",
        gateway=Gateway(),
        members=members,
        stage_bound=True,
        batch_enabled=batch,
    )
    assert not result.blocked
    assert len(calls) == len(result.pairs) == 1


async def test_same_parent_identity_with_changed_source_is_rejected():
    parents, members = sources(2)
    result = await screen_conflicts(
        parents + (parents[0].model_copy(update={"content": "另一个原文"}),),
        question="问题",
        gateway=object(),
        members=members,
        stage_bound=True,
    )
    assert result.blocked and result.errors == ("CONFLICT_SOURCE_IDENTITY_INVALID",)
