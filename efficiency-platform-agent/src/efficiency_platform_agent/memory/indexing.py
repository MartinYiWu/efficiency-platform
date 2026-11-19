"""显式有限索引工作；确认/GET/重启均不自动调用Embedding。"""

import asyncio
import hashlib
import time
from dataclasses import replace
from typing import Protocol

import httpx

from efficiency_platform_agent.core.context_dispatch import bind_context_send_guard
from efficiency_platform_agent.core.execution_control import current_run_control
from efficiency_platform_agent.core.memory_index import (
    IndexDelete,
    IndexLease,
    IndexUpsert,
    MemoryIndexWriter,
)
from efficiency_platform_agent.core.paid_budget import paid_scope
from efficiency_platform_agent.core.run_context_binding import current_run_context
from efficiency_platform_agent.core.task_authorization import TaskPaidBinding
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.providers.embedding.dashscope import (
    DashScopeEmbeddingProvider,
)
from efficiency_platform_agent.providers.paid_http import PaidHttpTransport


class MemoryIndexAuthority(Protocol):
    async def check_upsert(self, request: IndexUpsert) -> None:
        """Java内部认证、scope/源指纹/当前epoch/generation与原task/execution预算复验。"""
        ...

    async def check_delete(self, request: IndexDelete) -> None: ...


class MemoryIndexEmbedding(Protocol):
    async def embed_index(self, lease: IndexLease) -> tuple[float, ...]: ...


class GuardedMemoryIndexEmbedding:
    def __init__(
        self,
        provider: DashScopeEmbeddingProvider,
        ledger: SqlitePaidBudgetLedger,
        authority: MemoryIndexAuthority,
    ):
        self.provider, self.ledger = provider, ledger
        self.authority = authority
        self._transport()

    def _transport(self) -> PaidHttpTransport:
        provider = self.provider
        client = getattr(provider.client, "_client", None)
        transport = getattr(client, "_transport", None)
        if (
            type(provider) is not DashScopeEmbeddingProvider
            or type(client) is not httpx.AsyncClient
            or client.follow_redirects
            or client._mounts
            or type(transport) is not PaidHttpTransport
            or transport.ledger is not self.ledger
            or transport.provider != "embedding"
            or not transport.allowed_url
            or not transport.allowed_url.endswith("/embeddings")
            or getattr(provider.client, "max_retries", None) != 0
        ):
            raise ValueError("MEMORY_INDEX_GUARDED_EMBEDDING_REQUIRED")
        return transport

    async def embed_index(self, lease: IndexLease) -> tuple[float, ...]:
        return await self._embed(
            lease.request,
            lease.request.projection,
            lease.operation_id,
            lease.fingerprint,
            self.authority.check_upsert,
        )

    async def _embed(
        self, request, projection, operation_id, fingerprint, check
    ) -> tuple[float, ...]:
        if not self.ledger.task_authorization_enabled:
            raise ValueError("CONTINUATION_AUTH_UNSUPPORTED")
        transport = self._transport()
        if (
            self.provider.model != request.space.embedding_model
            or self.provider.dimensions != request.space.dimension
        ):
            raise ValueError("MEMORY_INDEX_EMBEDDING_SPACE_MISMATCH")
        binding, control = current_run_context(), current_run_control()
        if (
            binding is None
            or control is None
            or binding.conversation != request.execution.conversation
            or binding.task_id != request.execution.task_id
            or binding.execution_id != request.execution.execution_id
            or time.time() >= min(binding.deadline_epoch_seconds, request.expires_at)
        ):
            raise ValueError("MEMORY_INDEX_ORIGINAL_EXECUTION_REQUIRED")
        control.check()
        self.ledger.check_execution(
            request.scope.tenant_id, request.execution.execution_id
        )

        class Guard:
            def task_authorization_binding(self):
                return TaskPaidBinding(request.execution, operation_id, fingerprint)

            def check_live(self):
                control.check()
                if time.time() >= min(
                    binding.deadline_epoch_seconds, request.expires_at
                ):
                    raise ValueError("MEMORY_INDEX_AUTHORIZATION_EXPIRED")
                transport.ledger.check_execution(
                    request.scope.tenant_id, request.execution.execution_id
                )

            def before_reservation(self):
                self.check_live()

            async def before_send(self, payload):
                self.check_live()
                if (
                    payload.get("input") != [projection]
                    or payload.get("model") != request.space.embedding_model
                ):
                    raise ValueError("MEMORY_INDEX_EMBEDDING_INPUT_CHANGED")
                await check(request)
                self.check_live()

        async def send():
            with (
                bind_context_send_guard(Guard()),
                paid_scope(
                    (
                        "memory-query:"
                        if operation_id.startswith("memory-query-")
                        else "memory-index:"
                    )
                    + request.execution.task_id
                ),
            ):
                async with asyncio.timeout(
                    min(binding.deadline_epoch_seconds, request.expires_at)
                    - time.time()
                ):
                    vectors = await self.provider.embed((projection,))
            return vectors[0]

        return await control.execute(operation_id, send)


class GuardedMemoryQueryEmbedding(GuardedMemoryIndexEmbedding):
    def __init__(self, provider, ledger, authority, index):
        super().__init__(provider, ledger, authority)
        self.index = index
        self.query_authority = authority

    async def embed_query(self, request, query: str) -> tuple[float, ...]:
        if type(query) is not str or not query.strip() or len(query) > 2048:
            raise ValueError("MEMORY_RECALL_QUERY_INVALID")
        await self.query_authority.check(request)
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        cached = await self.index.claim_query(request, query_hash, preview=True)
        if cached is not None:
            if cached.vector is None:
                raise ValueError("MEMORY_QUERY_OPERATION_UNRESOLVED")
            return cached.vector
        transport = self._transport()
        binding = TaskPaidBinding(
            request.execution,
            "memory-query-preflight",
            hashlib.sha256(query.encode()).hexdigest(),
        )
        bid = self.ledger.task_budget_id(binding, transport.budget_id)
        snapshot = self.ledger.snapshot(bid)
        prices = snapshot.get("prices", [])
        price = next(
            (
                price
                for price in prices
                if price.get("provider") == "embedding"
                and price.get("model") == request.space.embedding_model
            ),
            None,
        )
        if (
            price is None
            or not price.get("pricing_version")
            or not price.get("pricing_source")
            or snapshot.get("stopped")
            or snapshot.get("remaining_calls", 0) < 1
            or snapshot.get("remaining_cost_microunits", 0)
            < price.get("max_cost_microunits_per_attempt", 1)
        ):
            raise ValueError("MEMORY_QUERY_PRICE_OR_BUDGET_REQUIRED")
        retention = await self.index.query_retention(request)
        lease = await self.index.claim_query(request, query_hash, expires_at=retention)
        if lease is None:
            raise ValueError("MEMORY_QUERY_OPERATION_UNRESOLVED")
        if lease.vector is not None:
            return lease.vector
        try:
            vector = await self._embed(
                replace(request, expires_at=min(request.expires_at, retention)),
                query,
                lease.operation_id,
                lease.fingerprint,
                self.query_authority.check,
            )
            await self.query_authority.check(request)
            await self.index.complete_query(lease, vector, request.space)
            return vector
        except BaseException:
            await self.index.fail_query_unknown(lease)
            raise


class MemoryIndexingService:
    def __init__(
        self,
        index: MemoryIndexWriter,
        authority: MemoryIndexAuthority,
        embedding: MemoryIndexEmbedding,
        *,
        enabled: bool = False,
        fixture: bool = False,
    ):
        if not fixture and type(embedding) is not GuardedMemoryIndexEmbedding:
            raise ValueError("MEMORY_INDEX_GUARDED_EMBEDDING_REQUIRED")
        if not fixture and getattr(embedding, "authority", None) is not authority:
            raise ValueError("MEMORY_INDEX_AUTHORITY_BINDING_REQUIRED")
        self.index, self.authority, self.embedding = index, authority, embedding
        self.enabled = enabled

    async def upsert(self, request: IndexUpsert) -> str:
        if not self.enabled:
            raise ValueError("MEMORY_INDEX_FEATURE_DISABLED")
        if time.time() >= request.expires_at:
            raise ValueError("MEMORY_INDEX_AUTHORIZATION_EXPIRED")
        await self.authority.check_upsert(request)
        lease = await self.index.claim(request)
        if lease.ready:
            return "READY"
        try:
            await self.authority.check_upsert(request)
            vector = await self.embedding.embed_index(lease)
            await self.authority.check_upsert(request)
            if time.time() >= request.expires_at:
                raise ValueError("MEMORY_INDEX_AUTHORIZATION_EXPIRED")
            await self.index.complete(lease, vector)
        except BaseException:
            # 取消/断线/崩溃不释放机会；unknown必须人工核对，不能自动重发。
            await self.index.fail_unknown(lease)
            raise
        return "READY"

    async def delete(self, request: IndexDelete) -> None:
        await self.authority.check_delete(request)
        await self.index.delete(request)
