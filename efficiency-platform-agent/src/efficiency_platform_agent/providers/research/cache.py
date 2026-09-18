"""租户与授权范围隔离的条件请求缓存端口。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from efficiency_platform_agent.contracts.research_sources_v2 import (
    FetchedContentV2,
    FetchRequestV2,
)

from ._adapter_support import ResearchDocumentFetcher
from .transport import ResearchFetchError


@dataclass(frozen=True, slots=True)
class ResponseCacheKey:
    tenant_id: str
    source_id: str
    url: str
    authorization_scope_digest: str
    cache_version: str


@dataclass(frozen=True, slots=True)
class CachedResponse:
    key: ResponseCacheKey
    content: FetchedContentV2
    expires_at: datetime

    def __post_init__(self) -> None:
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("CACHE_EXPIRY_NAIVE")
        if self.content.status_code != 200:
            raise ValueError("CACHE_CONTENT_STATUS_INVALID")


class ResponseCacheStore(Protocol):
    async def get(self, key: ResponseCacheKey) -> CachedResponse | None: ...

    async def put(self, entry: CachedResponse) -> None: ...


class InMemoryResponseCache:
    """仅供离线测试/单进程开发使用；不作为生产权威缓存。"""

    def __init__(self) -> None:
        self._entries: dict[ResponseCacheKey, CachedResponse] = {}

    async def get(self, key: ResponseCacheKey) -> CachedResponse | None:
        return self._entries.get(key)

    async def put(self, entry: CachedResponse) -> None:
        self._entries[entry.key] = entry


class ConditionalDocumentFetcher:
    def __init__(
        self,
        upstream: ResearchDocumentFetcher,
        store: ResponseCacheStore,
        *,
        cache_version: str,
        ttl: timedelta = timedelta(minutes=15),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not cache_version.strip() or ttl <= timedelta(0):
            raise ValueError("RESPONSE_CACHE_CONFIG_INVALID")
        self.upstream = upstream
        self.store = store
        self.cache_version = cache_version
        self.ttl = ttl
        self.clock = clock or (lambda: datetime.now(UTC))

    async def fetch(self, request: FetchRequestV2) -> FetchedContentV2:
        key = ResponseCacheKey(
            tenant_id=request.tenant_id,
            source_id=request.source_id,
            url=request.url,
            authorization_scope_digest=request.authorization_scope_digest,
            cache_version=self.cache_version,
        )
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("RESPONSE_CACHE_CLOCK_NAIVE")
        cached = await self.store.get(key)
        usable = cached is not None and cached.expires_at > now
        revalidatable = usable and cached is not None and bool(
            cached.content.etag or cached.content.last_modified
        )
        conditional = request
        if revalidatable and cached is not None:
            conditional = request.model_copy(
                update={
                    "etag": cached.content.etag,
                    "last_modified": cached.content.last_modified,
                }
            )
        response = await self.upstream.fetch(conditional)
        if (
            response.request_id != conditional.request_id
            or response.candidate_id != conditional.candidate_id
        ):
            raise ResearchFetchError(
                "SOURCE_SCHEMA_INVALID", "FETCH_RESPONSE_IDENTITY_MISMATCH"
            )
        if response.status_code == 304:
            if not revalidatable or cached is None:
                raise ResearchFetchError(
                    "CONTENT_UNAVAILABLE", "CACHE_REVALIDATION_MISS"
                )
            return cached.content.model_copy(
                update={
                    "request_id": request.request_id,
                    "candidate_id": request.candidate_id,
                    "fetched_at": response.fetched_at,
                    "etag": response.etag or cached.content.etag,
                    "last_modified": (
                        response.last_modified or cached.content.last_modified
                    ),
                    "downloaded_bytes": response.downloaded_bytes,
                    "request_count": response.request_count,
                    "cache_status": "revalidated",
                }
            )
        if response.status_code == 200:
            await self.store.put(
                CachedResponse(
                    key=key,
                    content=response,
                    expires_at=now + self.ttl,
                )
            )
        return response


__all__ = [
    "CachedResponse",
    "ConditionalDocumentFetcher",
    "InMemoryResponseCache",
    "ResponseCacheKey",
    "ResponseCacheStore",
]
