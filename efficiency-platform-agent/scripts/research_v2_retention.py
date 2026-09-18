"""Research V2 过期标记与内容最小化；默认只读 dry-run。"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from efficiency_platform_agent.persistence._postgres import validate_runtime_schema


@dataclass(frozen=True, slots=True)
class RetentionScope:
    tenant_id: str
    research_id: str
    before: datetime


@dataclass(frozen=True, slots=True)
class RetentionResult:
    matched: int
    updated: int


async def run_retention(
    connection: Any,
    schema: str,
    scope: RetentionScope,
    *,
    apply: bool = False,
) -> RetentionResult:
    """按显式 tenant/research/before 范围标记过期并移除受限正文。"""

    schema = validate_runtime_schema(schema)
    params = (scope.tenant_id, scope.research_id, scope.before)
    cursor = await connection.execute(
        f"SELECT count(*) FROM {schema}.research_artifacts "
        "WHERE tenant_id=%s AND research_id=%s AND expires_at<=%s "
        "AND expired_at IS NULL",
        params,
    )
    matched = int((await cursor.fetchone())[0])
    if not apply or matched == 0:
        return RetentionResult(matched, 0)
    cursor = await connection.execute(
        f"UPDATE {schema}.research_artifacts "
        "SET expired_at=clock_timestamp(),payload=payload-'content' "
        "WHERE tenant_id=%s AND research_id=%s AND expires_at<=%s "
        "AND expired_at IS NULL",
        params,
    )
    return RetentionResult(matched, cursor.rowcount)


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--research-id", required=True)
    parser.add_argument("--before", required=True)
    parser.add_argument("--schema", default="agent_runtime")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--authorization-ref")
    args = parser.parse_args()
    if args.apply and not args.authorization_ref:
        parser.error("--apply 必须同时提供 --authorization-ref")
    dsn = os.getenv("AGENT_X01_TEST_DATABASE_URL")
    if not dsn:
        parser.error("缺少 AGENT_X01_TEST_DATABASE_URL")
    connection = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
    try:
        result = await run_retention(
            connection,
            args.schema,
            RetentionScope(
                args.tenant_id,
                args.research_id,
                datetime.fromisoformat(args.before),
            ),
            apply=args.apply,
        )
        print(f"matched={result.matched} updated={result.updated} apply={args.apply}")
        return 0
    finally:
        await connection.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
