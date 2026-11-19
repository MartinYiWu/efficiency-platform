"""正式启动必须拒绝仅列存在、完整刷新防护缺失的真实双库。"""

import os

import pytest
from psycopg import sql
from sqlalchemy import text

from efficiency_platform_agent.harness.memory_runtime import build_memory_runtime
from tests.integration.memory.test_refresh_persistence import refresh_case  # noqa: F401
from tests.integration.memory.test_refresh_run_metadata import ops_case  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "broken",
    (
        None,
        "mysql_check",
        "mysql_trigger",
        "mysql_table",
        "pg_check",
        "pg_trigger",
        "pg_index",
        "pg_column",
    ),
)
async def test_real_refresh_startup_requires_enforced_schema(ops_case, broken):  # noqa: F811
    _, _, store, registry, _, _, _, saver, index, _ = ops_case
    official = await saver._saver.conn.execute("SELECT current_schema() AS name")
    official_schema = (await official.fetchone())["name"]
    restore = []
    if broken == "mysql_check":
        restore.append(
            "ALTER TABLE agent_memory_context_refresh ALTER CHECK ck_memory_refresh_receipt_phase ENFORCED"
        )
    elif broken in {"mysql_trigger", "mysql_table"}:
        async with store.engine.connect() as connection:
            if broken == "mysql_table":
                ddl = (
                    await connection.execute(
                        text("SHOW CREATE TABLE agent_memory_context_refresh")
                    )
                ).first()
                restore.append(ddl[1])
            for name in (
                (
                    "trg_memory_refresh_insert",
                    "trg_memory_refresh_update",
                    "trg_memory_refresh_delete",
                )
                if broken == "mysql_table"
                else ("trg_memory_refresh_insert",)
            ):
                ddl = (
                    (await connection.execute(text("SHOW CREATE TRIGGER " + name)))
                    .mappings()
                    .one()
                )
                restore.append(ddl["SQL Original Statement"])
    if broken == "mysql_check":
        async with store.engine.begin() as connection:
            await connection.execute(
                text(
                    "ALTER TABLE agent_memory_context_refresh ALTER CHECK ck_memory_refresh_receipt_phase NOT ENFORCED"
                )
            )
    elif broken == "mysql_trigger":
        async with store.engine.begin() as connection:
            await connection.execute(text("DROP TRIGGER trg_memory_refresh_insert"))
    elif broken == "mysql_table":
        async with store.engine.begin() as connection:
            await connection.execute(text("DROP TABLE agent_memory_context_refresh"))
    elif broken == "pg_check":
        await registry.connection.execute(
            "ALTER TABLE agent_memory_thread_resume DROP CONSTRAINT ck_memory_thread_resume_phase"
        )
    elif broken == "pg_trigger":
        await registry.connection.execute(
            "ALTER TABLE agent_memory_thread_execution DISABLE TRIGGER trg_memory_thread_refresh_execution"
        )
    elif broken == "pg_index":
        await registry.connection.execute(
            sql.SQL("DROP INDEX {}.uk_memory_thread_refresh_pending").format(
                sql.Identifier(registry.schema)
            )
        )
    elif broken == "pg_column":
        await registry.connection.execute(
            "ALTER TABLE agent_memory_thread_execution DROP COLUMN pending_resume_request_id CASCADE"
        )
    arguments = {
        "engine": store.engine,
        "memory_cipher": store.cipher,
        "checkpoint_key": bytes(range(32)),
        "checkpoint_key_version": "synthetic-startup",
        "postgres_dsn": os.environ["MEMORY_IT_POSTGRES_DSN"],
        "registry_schema": registry.schema,
        "official_schema": official_schema,
        "owned_schema": index._store.provider.schema,
        "refresh_enabled": True,
    }
    if broken is None:
        components = await build_memory_runtime(**arguments)
        try:
            assert components.refresh_service is not None
            assert components.send_authority is not None
            assert components.registry._wait_authority is components.refresh_service
        finally:
            await components.close()
    else:
        components = None
        try:
            with pytest.raises(ValueError, match="^MEMORY_REFRESH_SCHEMA_REQUIRED$"):
                components = await build_memory_runtime(**arguments)
        finally:
            if components is not None:
                await components.close()
            if restore:
                async with store.engine.begin() as connection:
                    for statement in restore:
                        await connection.execute(text(statement))
