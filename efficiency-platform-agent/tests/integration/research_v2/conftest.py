"""X01 真实 PostgreSQL 集成夹具。"""

from __future__ import annotations

import asyncio
import os
import selectors
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[3]


def pytest_asyncio_loop_factories(config, item):
    """Psycopg async 在 Windows 上要求 Selector 事件循环。"""

    del config, item
    if os.name == "nt":
        return {
            "windows-selector": lambda: asyncio.SelectorEventLoop(
                selectors.SelectSelector()
            )
        }
    return {"default": asyncio.new_event_loop}


@pytest.fixture
async def x01_connections():
    """只接受名称带 X01 隔离标记的数据库，避免误碰共享环境。"""

    dsn = os.getenv("AGENT_X01_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("未配置 AGENT_X01_TEST_DATABASE_URL")
    first = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
    second = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
    try:
        cursor = await first.execute("SELECT current_database()")
        database = (await cursor.fetchone())[0]
        if not str(database).startswith("efficiency_agent_x01_"):
            pytest.fail("X01 仅允许使用 efficiency_agent_x01_ 前缀的隔离数据库")
        for relative in (
            "sql/bootstrap/agent_database_bootstrap_v1/02-up.sql",
            "sql/changes/20260916_001_意图与研究V2/02-up.sql",
        ):
            await first.execute((ROOT / relative).read_text(encoding="utf-8"))
        await first.execute(
            "TRUNCATE agent_runtime.intent_states,agent_runtime.research_actions,"
            "agent_runtime.research_decisions,agent_runtime.research_artifacts,"
            "agent_runtime.budget_reservations,agent_runtime.budget_usage,"
            "agent_runtime.budget_ledgers,agent_runtime.checkpoints CASCADE"
        )
        yield first, second
    finally:
        await second.close()
        await first.close()
