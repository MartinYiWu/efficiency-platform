"""上下文集成仅显式启用，且只接本次专属MySQL schema。"""

import os
import re
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture
async def context_mysql():
    if os.environ.get("MEMORY_INTEGRATION_ENABLED") != "1":
        pytest.skip("MEMORY_INTEGRATION_ENABLED=1 required")
    value = os.environ.get("MEMORY_IT_MYSQL_URL")
    if not value:
        pytest.fail("explicit MEMORY_IT_MYSQL_URL required")
    url = make_url(value)
    if url.drivername != "mysql+asyncmy" or not re.fullmatch(
        r"aiep_memory_it_[0-9]{8}_[0-9a-f]{10}", url.database or ""
    ):
        pytest.fail("dedicated synthetic memory integration schema required")
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            count = (
                await connection.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=:schema"
                    ),
                    {"schema": url.database},
                )
            ).scalar_one()
            if count != 0:
                pytest.fail("dedicated schema must be empty; existing tables preserved")
            root = Path(__file__).resolve().parents[3]
            for topic in ("context_control_v1", "context_stage_v1"):
                raw = (root / "sql/bootstrap" / topic / "02-up.sql").read_text(
                    encoding="utf-8"
                )
                sql = re.sub(r"--[^\n]*", "", raw)
                for statement in sql.split(";"):
                    if statement.strip():
                        await connection.execute(text(statement))
        yield engine
    finally:
        await engine.dispose()
