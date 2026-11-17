"""仅显式本机隔离schema的真实生产记忆组件fixture，不替换registry/ACK。"""

import base64
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from psycopg import AsyncConnection, sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from efficiency_platform_agent.harness.memory_runtime import build_memory_runtime
from efficiency_platform_agent.orchestration.memory_saver_factory import (
    create_official_saver,
)


@asynccontextmanager
async def production_memory_runtime(engine, cipher):
    dsn = os.environ.get("MEMORY_IT_POSTGRES_DSN", "")
    if os.environ.get("MEMORY_IT_ALLOW_SCHEMA_DDL") != "1" or conninfo_to_dict(dsn).get(
        "host"
    ) not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("MEMORY_IT_EXPLICIT_LOCAL_POSTGRES_REQUIRED")
    admin = await AsyncConnection.connect(
        dsn,
        autocommit=True,
        row_factory=dict_row,
        prepare_threshold=0,
        connect_timeout=5,
    )
    suffix = uuid4().hex[:8]
    registry, official, owned = (
        "memory_it_d17_registry_" + suffix,
        "memory_it_d17_official_" + suffix,
        "agent_runtime_" + suffix,
    )
    created = []
    components = None
    try:
        for name in (registry, official, owned):
            await admin.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name))
            )
            created.append(name)
        await admin.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(registry))
        )
        for topic in ("memory_thread_v1", "memory_thread_capability_v1"):
            script = (
                Path(__file__).parents[3] / "sql/bootstrap" / topic / "02-up.sql"
            ).read_text(encoding="utf-8")
            for statement in script.split(";"):
                if statement.strip():
                    await admin.execute(statement)
        await admin.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(official))
        )
        await create_official_saver(admin).setup()
        await admin.execute(
            sql.SQL(
                "CREATE TABLE {}.checkpoints(thread_id text NOT NULL,tenant_id text NOT NULL,checkpoint_ns text NOT NULL,checkpoint_id text NOT NULL,state jsonb NOT NULL,PRIMARY KEY(tenant_id,thread_id,checkpoint_ns))"
            ).format(sql.Identifier(owned))
        )
        components = await build_memory_runtime(
            engine=engine,
            memory_cipher=cipher,
            checkpoint_key=base64.b64decode(
                os.environ["MEMORY_IT_MEMORY_ENCRYPTION_KEY"], validate=True
            ),
            checkpoint_key_version="isolated-checkpoint",
            postgres_dsn=dsn,
            registry_schema=registry,
            official_schema=official,
            owned_schema=owned,
        )
        yield components
    finally:
        if components is not None:
            await components.close()
        for name in reversed(created):
            await admin.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name))
            )
        await admin.close()
