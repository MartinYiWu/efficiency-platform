"""DashScope 文本重排 Provider；检索阶段通过此边界接入。"""

from __future__ import annotations

from typing import Any


class RerankProviderError(RuntimeError):
    code = "RERANK_PROVIDER_FAILED"


class DashScopeRerankProvider:
    def __init__(self, client: Any, *, model: str = "qwen3-rerank") -> None:
        self.client = client
        self.model = model

    async def rerank(
        self, query: str, documents: tuple[str, ...], *, top_n: int
    ) -> tuple[tuple[int, float], ...]:
        if not query.strip() or not documents or top_n < 1:
            raise ValueError("RERANK_INPUT_INVALID")
        try:
            response = await self.client.rerank(
                model=self.model,
                query=query,
                documents=list(documents),
                top_n=min(top_n, len(documents)),
            )
            return tuple(
                (int(item.index), float(item.relevance_score))
                for item in response.results
            )
        except Exception as error:
            raise RerankProviderError("重排服务调用失败") from error


__all__ = ["DashScopeRerankProvider", "RerankProviderError"]
