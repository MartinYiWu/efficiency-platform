"""冻结索引范围内的查询改写、双路召回、RRF 与重排。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from .intent import StructuredStageGateway
from .release_bundle import CustomerServiceReleaseBundle
from .state import Evidence, QueryRewrite


class EmbeddingPort(Protocol):
    async def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class RerankPort(Protocol):
    async def rerank(
        self, query: str, documents: tuple[str, ...], *, top_n: int
    ) -> tuple[tuple[int, float], ...]: ...


class RetrievalRepository(Protocol):
    async def vector_search(
        self,
        *,
        tenant_id: str,
        index_release_ids: tuple[UUID, ...],
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[Evidence, ...]: ...

    async def fts_search(
        self,
        *,
        tenant_id: str,
        index_release_ids: tuple[UUID, ...],
        query: str,
        limit: int,
    ) -> tuple[Evidence, ...]: ...


@dataclass(frozen=True, slots=True)
class RetrievalTrace:
    original_query: str
    rewritten_queries: tuple[str, ...]
    index_release_ids: tuple[UUID, ...]
    vector_candidates: tuple[Evidence, ...]
    fts_candidates: tuple[Evidence, ...]
    fused_candidates: tuple[Evidence, ...]
    reranked_evidence: tuple[Evidence, ...]


class CustomerServiceRetrieval:
    def __init__(
        self,
        repository: RetrievalRepository,
        embedding: EmbeddingPort,
        reranker: RerankPort,
    ) -> None:
        self.repository = repository
        self.embedding = embedding
        self.reranker = reranker

    async def search(
        self,
        *,
        tenant_id: str,
        question: str,
        gateway: StructuredStageGateway,
        bundle: CustomerServiceReleaseBundle,
    ) -> RetrievalTrace:
        policy = bundle.rag_policy
        rewrite = await gateway.complete(
            "rewrite",
            {"question": question, "rewrite_query_limit": policy.rewrite_query_limit},
            QueryRewrite,
        )
        queries = rewrite.queries[: policy.rewrite_query_limit]
        vectors = await self.embedding.embed(queries)
        release_ids = tuple(item.index_release_id for item in bundle.knowledge_bindings)
        rankings: list[tuple[Evidence, ...]] = []
        vector_candidates: list[Evidence] = []
        fts_candidates: list[Evidence] = []
        for query, vector in zip(queries, vectors, strict=True):
            vector_items = await self.repository.vector_search(
                tenant_id=tenant_id,
                index_release_ids=release_ids,
                vector=vector,
                limit=policy.vector_top_k,
            )
            fts_items = await self.repository.fts_search(
                tenant_id=tenant_id,
                index_release_ids=release_ids,
                query=query,
                limit=policy.fts_top_k,
            )
            rankings.extend((vector_items, fts_items))
            vector_candidates.extend(vector_items)
            fts_candidates.extend(fts_items)
        fused = _rrf(rankings)[: policy.fusion_top_k]
        if not fused:
            return RetrievalTrace(
                question,
                queries,
                release_ids,
                tuple(vector_candidates),
                tuple(fts_candidates),
                (),
                (),
            )
        reranked = await self.reranker.rerank(
            question,
            tuple(item.content for item in fused),
            top_n=min(policy.rerank_top_k, len(fused)),
        )
        evidence = tuple(
            fused[index].model_copy(update={"score": score})
            for index, score in reranked
        )
        return RetrievalTrace(
            question,
            queries,
            release_ids,
            tuple(vector_candidates),
            tuple(fts_candidates),
            tuple(fused),
            evidence,
        )


def _rrf(rankings: list[tuple[Evidence, ...]], constant: int = 60) -> list[Evidence]:
    scores: dict[UUID, float] = {}
    values: dict[UUID, Evidence] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            values[item.chunk_id] = item
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + 1.0 / (
                constant + rank
            )
    return [
        values[key].model_copy(update={"score": score})
        for key, score in sorted(
            scores.items(), key=lambda pair: (-pair[1], str(pair[0]))
        )
    ]


__all__ = [
    "CustomerServiceRetrieval",
    "RetrievalRepository",
    "RetrievalTrace",
]
