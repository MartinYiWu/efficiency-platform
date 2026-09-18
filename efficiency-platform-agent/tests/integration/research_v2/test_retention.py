"""X01 保留策略默认 dry-run 与显式 apply。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from scripts.research_v2_retention import RetentionScope, run_retention


async def test_retention_dry_run_does_not_mutate_and_apply_marks_expired(
    x01_connections,
) -> None:
    first, _ = x01_connections
    now = datetime.now(UTC)
    await first.execute(
        "INSERT INTO agent_runtime.research_artifacts "
        "(tenant_id,research_id,artifact_id,artifact_kind,payload,expires_at) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        (
            "tenant-retention",
            "research-retention",
            "html-1",
            "raw_html",
            Jsonb({"content": "private-html", "url": "https://example.com"}),
            now - timedelta(seconds=1),
        ),
    )
    scope = RetentionScope("tenant-retention", "research-retention", now)
    dry = await run_retention(first, "agent_runtime", scope, apply=False)
    assert dry.matched == 1
    cursor = await first.execute(
        "SELECT expired_at FROM agent_runtime.research_artifacts "
        "WHERE tenant_id=%s AND artifact_id=%s",
        ("tenant-retention", "html-1"),
    )
    assert (await cursor.fetchone())[0] is None

    applied = await run_retention(first, "agent_runtime", scope, apply=True)
    assert applied.updated == 1
    cursor = await first.execute(
        "SELECT expired_at, payload ? 'content' "
        "FROM agent_runtime.research_artifacts "
        "WHERE tenant_id=%s AND artifact_id=%s",
        ("tenant-retention", "html-1"),
    )
    expired_at, has_content = await cursor.fetchone()
    assert expired_at is not None
    assert has_content is False
