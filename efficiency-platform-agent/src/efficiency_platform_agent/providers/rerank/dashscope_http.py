"""DashScope 文本重排 HTTP 客户端。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


class DashScopeRerankHttpClient:
    def __init__(self, client: Any, *, api_key: str, base_url: str) -> None:
        self.client = client
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def rerank(
        self, *, model: str, query: str, documents: list[str], top_n: int
    ) -> Any:
        response = await self.client.post(
            self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": model,
                "input": {"query": query, "documents": documents},
                "parameters": {"top_n": top_n, "return_documents": False},
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("output", {}).get("results")
        if not isinstance(results, list):
            raise TypeError("RERANK_RESPONSE_INVALID")
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    index=item["index"], relevance_score=item["relevance_score"]
                )
                for item in results
            ]
        )


__all__ = ["DashScopeRerankHttpClient"]
