"""X01 动作恢复和 UNKNOWN_OUTCOME 语义。"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys

from efficiency_platform_agent.orchestration.postgres_checkpoint import (
    PostgresCheckpointStore,
)
from efficiency_platform_agent.persistence.research import PostgresResearchRepository


async def test_call_finished_before_commit_is_unknown_and_not_blindly_replayed(
    x01_connections,
) -> None:
    first, second = x01_connections
    repo_a = PostgresResearchRepository(first, "agent_runtime")
    repo_b = PostgresResearchRepository(second, "agent_runtime")
    await repo_a.claim_action(
        tenant_id="tenant-a",
        research_id="research-crash",
        action_fingerprint="fingerprint-crash",
        invocation_id="invocation-crash",
        lease_owner="worker-a",
        request={"query": "AI"},
    )
    unknown = await repo_a.mark_unknown_outcome(
        tenant_id="tenant-a",
        research_id="research-crash",
        action_fingerprint="fingerprint-crash",
        lease_owner="worker-a",
        conservative_charge={"calls": 1, "unknown": True},
    )

    recovered = await repo_b.claim_action(
        tenant_id="tenant-a",
        research_id="research-crash",
        action_fingerprint="fingerprint-crash",
        invocation_id="invocation-crash",
        lease_owner="worker-b",
        request={"query": "AI"},
    )
    assert unknown.status == "UNKNOWN_OUTCOME"
    assert recovered.claimed is False
    assert recovered.action.status == "UNKNOWN_OUTCOME"


async def test_fact_commit_does_not_imply_checkpoint_commit(x01_connections) -> None:
    first, _ = x01_connections
    repo = PostgresResearchRepository(first, "agent_runtime")
    await repo.claim_action(
        tenant_id="tenant-a",
        research_id="research-fact-only",
        action_fingerprint="fingerprint-fact-only",
        invocation_id="invocation-fact-only",
        lease_owner="worker-a",
        request={},
    )
    await repo.commit_action(
        tenant_id="tenant-a",
        research_id="research-fact-only",
        action_fingerprint="fingerprint-fact-only",
        lease_owner="worker-a",
        result={"ok": True},
    )
    cursor = await first.execute(
        "SELECT count(*) FROM agent_runtime.checkpoints "
        "WHERE tenant_id=%s AND thread_id=%s",
        ("tenant-a", "research-fact-only"),
    )
    assert (await cursor.fetchone())[0] == 0

    store = PostgresCheckpointStore(first, "agent_runtime")
    saved = await store.save(
        "research-fact-only",
        "research-v2:1",
        {"phase": "evidence"},
        tenant_id="tenant-a",
        checkpoint_id="checkpoint-fact-only",
    )
    restored = await store.get(
        "research-fact-only", "research-v2:1", tenant_id="tenant-a"
    )
    assert saved.checkpoint_id == "checkpoint-fact-only"
    assert restored is not None
    assert restored.state["phase"] == "evidence"


async def test_committed_action_is_visible_after_process_restart(
    x01_connections,
) -> None:
    first, _ = x01_connections
    repo = PostgresResearchRepository(first, "agent_runtime")
    await repo.claim_action(
        tenant_id="tenant-process",
        research_id="research-process",
        action_fingerprint="fingerprint-process",
        invocation_id="invocation-process",
        lease_owner="worker-parent",
        request={"query": "restart"},
    )
    await repo.commit_action(
        tenant_id="tenant-process",
        research_id="research-process",
        action_fingerprint="fingerprint-process",
        lease_owner="worker-parent",
        result={"persisted": True},
    )
    code = (
        "import os, psycopg; "
        "c=psycopg.connect(os.environ['AGENT_X01_TEST_DATABASE_URL']); "
        "r=c.execute(\"SELECT status FROM agent_runtime.research_actions "
        "WHERE tenant_id=%s AND research_id=%s AND action_fingerprint=%s\", "
        "('tenant-process','research-process','fingerprint-process')).fetchone(); "
        "print(r[0]); c.close()"
    )
    process = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-c", code],
        env=dict(os.environ),
        capture_output=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr.decode()
    assert process.stdout.decode().strip() == "COMMITTED"
