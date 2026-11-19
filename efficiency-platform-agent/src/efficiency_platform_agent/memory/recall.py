"""Java合法集合内的索引召回；只返引用，正文仍须Java当前权限二次hydrate。"""

import time
from dataclasses import dataclass
from typing import Literal, Protocol

from efficiency_platform_agent.core.memory_index import (
    AuthorizedMemoryRecall,
    MemoryIndexReader,
    MemoryRecallCandidate,
    validate_memory_vector,
)
from efficiency_platform_agent.memory.ranking import fuse_memory_candidates

__all__ = [
    "AuthorizedMemoryRecall",
    "MemoryQueryEmbedding",
    "MemoryRecallAuthority",
    "MemoryRecallResult",
    "MemoryRecallService",
]


class MemoryRecallAuthority(Protocol):
    async def check(self, request: AuthorizedMemoryRecall) -> None:
        """原执行/Java认证snapshot与当前源/撤权复核；不能信HTTP的allowed数组。"""
        ...


class MemoryQueryEmbedding(Protocol):
    async def embed_query(
        self, request: AuthorizedMemoryRecall, query: str
    ) -> tuple[float, ...]:
        """原task唯一查询机会、原授权总账/窗口/截止；不自行续额。"""
        ...


@dataclass(frozen=True, slots=True)
class MemoryRecallResult:
    candidates: tuple[MemoryRecallCandidate, ...]
    query_embedding_status: Literal["NOT_REQUESTED", "USED"]
    legal_count: int
    elapsed_ms: float
    hydration_required: Literal[True] = True


class MemoryRecallService:
    def __init__(
        self,
        index: MemoryIndexReader,
        authority: MemoryRecallAuthority,
        query_embedding: MemoryQueryEmbedding | None = None,
        *,
        enabled: bool = False,
    ):
        self.index, self.authority = index, authority
        self.query_embedding, self.enabled = query_embedding, enabled

    async def recall(
        self,
        request: AuthorizedMemoryRecall,
        *,
        terms: tuple[str, ...] = (),
        query: str | None = None,
    ) -> MemoryRecallResult:
        if not self.enabled:
            raise ValueError("MEMORY_RECALL_FEATURE_DISABLED")
        if (
            type(request) is not AuthorizedMemoryRecall
            or time.time() >= request.expires_at
        ):
            raise ValueError("MEMORY_RECALL_AUTHORIZATION_EXPIRED")
        if (
            type(terms) is not tuple
            or len(terms) > 32
            or any(
                type(term) is not str or not term.strip() or len(term) > 128
                for term in terms
            )
        ):
            raise ValueError("MEMORY_RECALL_QUERY_INVALID")
        if query is not None and (
            type(query) is not str or not query.strip() or len(query) > 2048
        ):
            raise ValueError("MEMORY_RECALL_QUERY_INVALID")
        started = time.monotonic()
        await self.authority.check(request)
        if not request.allowed:
            return MemoryRecallResult(
                (), "NOT_REQUESTED", 0, (time.monotonic() - started) * 1000
            )
        vector = None
        status: Literal["NOT_REQUESTED", "USED"] = "NOT_REQUESTED"
        if query is not None:
            if not request.query_embedding_allowed or self.query_embedding is None:
                raise ValueError("MEMORY_QUERY_EMBEDDING_NOT_AUTHORIZED")
            vector = await self.query_embedding.embed_query(request, query)
            validate_memory_vector(vector, request.space)
            status = "USED"
        await self.authority.check(request)
        if time.time() >= request.expires_at:
            raise ValueError("MEMORY_RECALL_AUTHORIZATION_EXPIRED")
        vector_items, lexical_items = await self.index.search(
            request.scope,
            request.space,
            request.allowed,
            vector=vector,
            terms=terms,
            limit=30,
        )
        await self.authority.check(request)
        if time.time() >= request.expires_at:
            raise ValueError("MEMORY_RECALL_AUTHORIZATION_EXPIRED")
        candidates = fuse_memory_candidates(
            vector_items, lexical_items, request.allowed, top_k=request.top_k
        )
        return MemoryRecallResult(
            candidates,
            status,
            len(request.allowed),
            (time.monotonic() - started) * 1000,
        )
