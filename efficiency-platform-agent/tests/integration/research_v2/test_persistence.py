"""X01 意图与研究事实的双连接集成测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from efficiency_platform_agent.contracts.intent_v2 import IntentFrameV2
from efficiency_platform_agent.persistence.intent_state import (
    IntentStateScope,
    PostgresIntentStateRepository,
)
from efficiency_platform_agent.persistence.research import (
    PostgresResearchRepository,
)


def _frame(revision: int, message_id: str) -> IntentFrameV2:
    return IntentFrameV2(
        task_id="task-1",
        revision=revision,
        message_id=message_id,
        anchor_time=datetime(2026, 9, 17, tzinfo=UTC),
        timezone="Asia/Shanghai",
        dialog_act="chat",
    )


async def test_two_connections_enforce_revision_cas_and_tenant_isolation(
    x01_connections,
) -> None:
    first, second = x01_connections
    repo_a = PostgresIntentStateRepository(first, "agent_runtime")
    repo_b = PostgresIntentStateRepository(second, "agent_runtime")
    scope = IntentStateScope("tenant-a")

    assert await repo_a.compare_and_set(scope, 0, _frame(1, "message-1"))
    assert await repo_b.get(IntentStateScope("tenant-b"), "task-1") is None
    assert await repo_a.compare_and_set(scope, 1, _frame(2, "message-2"))
    assert not await repo_b.compare_and_set(scope, 1, _frame(2, "message-3"))


async def test_committed_action_replays_without_cross_tenant_visibility(
    x01_connections,
) -> None:
    first, second = x01_connections
    repo_a = PostgresResearchRepository(first, "agent_runtime")
    repo_b = PostgresResearchRepository(second, "agent_runtime")

    claimed = await repo_a.claim_action(
        tenant_id="tenant-a",
        research_id="research-1",
        action_fingerprint="fingerprint-1",
        invocation_id="invocation-1",
        lease_owner="worker-a",
        request={"query": "AI"},
    )
    assert claimed.claimed is True
    committed = await repo_a.commit_action(
        tenant_id="tenant-a",
        research_id="research-1",
        action_fingerprint="fingerprint-1",
        lease_owner="worker-a",
        result={"items": 1},
    )
    replay = await repo_b.claim_action(
        tenant_id="tenant-a",
        research_id="research-1",
        action_fingerprint="fingerprint-1",
        invocation_id="invocation-1",
        lease_owner="worker-b",
        request={"query": "AI"},
    )
    assert committed.status == "COMMITTED"
    assert replay.claimed is False
    assert replay.action == committed
    assert await repo_b.get_action("tenant-b", "research-1", "fingerprint-1") is None


async def test_rollback_switch_blocks_new_writes_but_keeps_old_reads(
    x01_connections,
) -> None:
    first, _ = x01_connections
    repo = PostgresIntentStateRepository(first, "agent_runtime")
    scope = IntentStateScope("tenant-rollback")
    original = _frame(1, "message-before-rollback")
    assert await repo.compare_and_set(scope, 0, original)
    await first.execute(
        "UPDATE agent_runtime.feature_controls SET enabled=FALSE "
        "WHERE feature_name='intent_research_v2_writes'"
    )
    try:
        assert await repo.get(scope, "task-1") == original
        with pytest.raises(RuntimeError, match="INTENT_RESEARCH_V2_WRITES_DISABLED"):
            await repo.compare_and_set(
                scope, 1, _frame(2, "message-after-rollback")
            )
    finally:
        await first.execute(
            "UPDATE agent_runtime.feature_controls SET enabled=TRUE "
            "WHERE feature_name='intent_research_v2_writes'"
        )
