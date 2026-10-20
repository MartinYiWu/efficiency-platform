"""DashScope OpenAI 兼容 Embedding Provider。"""

from __future__ import annotations

from typing import Any


class EmbeddingProviderError(RuntimeError):
    code = "EMBEDDING_PROVIDER_FAILED"


class DashScopeEmbeddingProvider:
    """封装厂商请求并只向上返回固定维度浮点向量。"""

    def __init__(
        self,
        client: Any,
        *,
        model: str = "text-embedding-v4",
        dimensions: int = 1024,
    ) -> None:
        if model != "text-embedding-v4" or dimensions != 1024:
            raise ValueError("EMBEDDING_SPACE_INVALID")
        self.client = client
        self.model = model
        self.dimensions = dimensions

    async def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("EMBEDDING_INPUT_INVALID")
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=list(texts),
                dimensions=self.dimensions,
                encoding_format="float",
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors = tuple(
                tuple(float(value) for value in item.embedding) for item in ordered
            )
        except Exception as error:
            raise EmbeddingProviderError("Embedding 服务调用失败") from error
        if len(vectors) != len(texts):
            raise EmbeddingProviderError("Embedding 返回数量不一致")
        if any(len(vector) != self.dimensions for vector in vectors):
            raise EmbeddingProviderError("Embedding 返回维度不一致")
        return vectors


__all__ = ["DashScopeEmbeddingProvider", "EmbeddingProviderError"]
