"""核对智能客服在 Agent MySQL 和 pgvector 中的真实持久化结果。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import psycopg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def load_env(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def mysql_facts(url: str) -> dict[str, Any]:
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            release_rows = (
                await connection.execute(
                    text(
                        "SELECT release_id,agent_version,graph_version,status "
                        "FROM agent_release_bundle WHERE agent_key='customer-service' "
                        "ORDER BY created_at_epoch_ms DESC LIMIT 5"
                    )
                )
            ).all()
            run_rows = (
                await connection.execute(
                    text("SELECT status,COUNT(*) FROM agent_run GROUP BY status ORDER BY status")
                )
            ).all()
            snapshot_count = (
                await connection.execute(
                    text("SELECT COUNT(*) FROM agent_customer_service_retrieval_snapshot")
                )
            ).scalar_one()
    finally:
        await engine.dispose()
    if not release_rows:
        raise RuntimeError("AGENT_MYSQL_RELEASE_FACTS_MISSING")
    if int(snapshot_count) < 1:
        raise RuntimeError("AGENT_MYSQL_RETRIEVAL_FACTS_MISSING")
    if not run_rows:
        raise RuntimeError("AGENT_MYSQL_RUN_FACTS_MISSING")
    return {
        "customer_service_release_count_sampled": len(release_rows),
        "latest_releases": [
            {
                "release_id": str(row[0]),
                "agent_version": str(row[1]),
                "graph_version": str(row[2]),
                "status": str(row[3]),
            }
            for row in release_rows
        ],
        "run_status_counts": {str(row[0]): int(row[1]) for row in run_rows},
        "retrieval_snapshot_count": int(snapshot_count),
    }


def vector_facts(url: str, release_ids: tuple[str, ...]) -> dict[str, Any]:
    normalized = url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(normalized) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT m.index_release_id::text,COUNT(DISTINCT m.document_version_id),"
            "COUNT(c.chunk_id),MIN(vector_dims(c.embedding)),MAX(vector_dims(c.embedding)) "
            "FROM customer_service.index_release_document m "
            "JOIN customer_service.document_chunk c "
            "ON c.document_version_id=m.document_version_id "
            "WHERE m.index_release_id=ANY(%s::uuid[]) "
            "GROUP BY m.index_release_id ORDER BY m.index_release_id",
            (list(release_ids),),
        )
        rows = cursor.fetchall()
    found = {str(row[0]) for row in rows}
    if found != set(release_ids):
        raise RuntimeError("PGVECTOR_INDEX_RELEASE_FACTS_MISSING")
    if any(int(row[2]) < 1 or int(row[3]) != 1024 or int(row[4]) != 1024 for row in rows):
        raise RuntimeError("PGVECTOR_CHUNK_OR_DIMENSION_INVALID")
    return {
        "index_releases": [
            {
                "release_id": str(row[0]),
                "document_version_count": int(row[1]),
                "chunk_count": int(row[2]),
                "embedding_dimension_min": int(row[3]),
                "embedding_dimension_max": int(row[4]),
            }
            for row in rows
        ]
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--release-id", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load_env(args.env_file)
    mysql_url = os.environ.get("AGENT_RUNTIME_DATABASE_URL", "")
    vector_url = os.environ.get("AGENT_VECTOR_DATABASE_URL", "")
    if not mysql_url or not vector_url:
        raise RuntimeError("CUSTOMER_SERVICE_DATABASE_URL_MISSING")
    result = {
        "agent_mysql": await mysql_facts(mysql_url),
        "pgvector": vector_facts(vector_url, tuple(args.release_id)),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
