"""Agent Runtime PostgreSQL 持久化的最小安全公共函数。"""

from __future__ import annotations

import re
from typing import Any

_RUNTIME_SCHEMA = re.compile(r"^agent_runtime(?:_[a-f0-9]{8})?$")


def validate_runtime_schema(schema: str) -> str:
    """仅允许固定 Agent Runtime schema 及隔离验收后缀。"""

    if not isinstance(schema, str) or _RUNTIME_SCHEMA.fullmatch(schema) is None:
        raise ValueError("Schema 必须是 agent_runtime 或带八位十六进制隔离后缀")
    return schema


async def fetchone(
    connection: Any, sql: str, params: tuple[object, ...] = ()
) -> tuple[Any, ...] | None:
    cursor = await connection.execute(sql, params)
    row = await cursor.fetchone()
    return tuple(row) if row is not None else None


async def ensure_writes_enabled(connection: Any, schema: str) -> None:
    row = await fetchone(
        connection,
        f"SELECT enabled FROM {schema}.feature_controls "
        "WHERE feature_name = %s FOR SHARE",
        ("intent_research_v2_writes",),
    )
    if row is None or row[0] is not True:
        raise RuntimeError("INTENT_RESEARCH_V2_WRITES_DISABLED")


__all__ = ["ensure_writes_enabled", "fetchone", "validate_runtime_schema"]
