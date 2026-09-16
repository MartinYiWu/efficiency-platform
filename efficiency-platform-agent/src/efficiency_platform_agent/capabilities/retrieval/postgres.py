"""PostgreSQL pgvector 与原生 FTS 双路检索适配器。"""

from __future__ import annotations

import inspect
from typing import Any

from efficiency_platform_agent.providers.database.postgres import PostgresProvider


class PostgresRetrievalProvider:
    """固定 text-embedding-v4/1024/cosine 向量空间的租户隔离检索。"""

    def __init__(self, connection: Any, schema: str, *, dimension: int = 1024) -> None:
        if dimension != 1024:
            raise ValueError("S7 向量维度固定为 1024")
        self.provider = PostgresProvider(connection, schema)
        self.dimension = dimension

    async def search(
        self,
        *,
        tenant_id: str,
        query_vector: list[float],
        query_text: str,
        top_k: int = 10,
    ) -> tuple[dict[str, Any], ...]:
        if len(query_vector) != self.dimension:
            raise ValueError("查询向量维度必须为 1024")
        if not 1 <= top_k <= 100:
            raise ValueError("top_k 必须在 1 至 100 之间")
        vector_literal = "[" + ",".join(str(value) for value in query_vector) + "]"
        sql = (
            f"SELECT chunk_id, document_id, content, "
            f"(embedding <=> %s::vector) AS distance, "
            f"ts_rank(to_tsvector('simple', content), plainto_tsquery('simple', %s)) AS fts_rank "
            f"FROM {self.provider.schema}.chunks "
            "WHERE tenant_id = %s AND embedding_model = %s AND embedding_dimension = %s "
            "ORDER BY (embedding <=> %s::vector), fts_rank DESC LIMIT %s"
        )
        result = self.provider.connection.execute(
            sql,
            (
                vector_literal,
                query_text,
                tenant_id,
                "text-embedding-v4",
                self.dimension,
                vector_literal,
                top_k,
            ),
        )
        if inspect.isawaitable(result):
            result = await result
        return tuple(result or ())

    async def close(self) -> None:
        """释放注入连接或连接池。"""
        await self.provider.close()


__all__ = ["PostgresRetrievalProvider"]
