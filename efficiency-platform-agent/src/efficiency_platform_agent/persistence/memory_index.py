"""Agent自有PG索引：持久claim、删除水位、精确合法集检索；不保存业务正文。"""

import asyncio
import hashlib
import inspect
import json
import math
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict

from psycopg.pq import PipelineStatus, TransactionStatus

from efficiency_platform_agent.core.memory_index import (
    IndexDelete,
    IndexLease,
    IndexUpsert,
    MemoryIndexIdentity,
    MemoryIndexScope,
    MemoryIndexSpace,
    MemoryRecallCandidate,
    QueryEmbeddingLease,
    validate_memory_vector,
)
from efficiency_platform_agent.providers.database.postgres import PostgresProvider


def index_fingerprint(request: IndexUpsert) -> str:
    value = {
        "scope": request.scope.key,
        "space": asdict(request.space),
        "identity": asdict(request.identity),
        "projection": request.projection,
        "terms": request.terms,
        "retention_expires_at": request.retention_expires_at,
    }
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


class PostgresMemoryIndex:
    async def expire(
        self, scope: MemoryIndexScope | None, *, now: int, limit: int = 100
    ) -> dict:
        if (
            type(now) is not int
            or now < 1
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise ValueError("MEMORY_INDEX_EXPIRY_BOUNDS_INVALID")
        receipts = []
        condition = "scope_key=%s AND " if scope is not None else ""
        scope_params = (scope.key,) if scope is not None else ()
        async with self._transaction():
            # 同claim固定fence→entry顺序；同批多个清理worker的重复回执保持幂等。
            cursor = await self._execute(
                "SELECT scope_key,embedding_model,dimension,policy_version,item_id,generation,version_id,deletion_epoch FROM {schema}.memory_index_entries WHERE "
                + condition
                + "expires_at<=%s ORDER BY expires_at,scope_key,item_id LIMIT %s",
                (*scope_params, now, limit),
            )
            rows = cursor.fetchall()
            rows = tuple(await rows if inspect.isawaitable(rows) else rows)
            for (
                scope_key,
                model,
                dimension,
                policy,
                item,
                generation,
                version,
                epoch,
            ) in rows:
                fence = await self._fence(scope_key, item)
                if (fence[0], fence[1]) == (generation, epoch):
                    await self._execute(
                        "UPDATE {schema}.memory_index_fences SET deleted=TRUE WHERE scope_key=%s AND item_id=%s",
                        (scope_key, item),
                    )
                key = (scope_key, model, dimension, policy, item, generation)
                await self._execute(
                    "DELETE FROM {schema}.memory_index_entries WHERE scope_key=%s AND embedding_model=%s AND dimension=%s AND policy_version=%s AND item_id=%s AND generation=%s AND expires_at<=%s",
                    (*key, now),
                )
                await self._execute(
                    "UPDATE {schema}.memory_index_jobs SET state='DELETED' WHERE scope_key=%s AND embedding_model=%s AND dimension=%s AND policy_version=%s AND item_id=%s AND generation=%s AND state='READY'",
                    key,
                )
                identity = {
                    "scope_key": scope_key,
                    "embedding_model": model,
                    "dimension": dimension,
                    "policy_version": policy,
                    "item_id": item,
                    "generation": generation,
                    "version_id": version,
                    "deletion_epoch": epoch,
                }
                event = (
                    "memory-expiry-"
                    + hashlib.sha256(
                        json.dumps(
                            identity, sort_keys=True, separators=(",", ":")
                        ).encode()
                    ).hexdigest()
                )
                receipts.append(
                    {
                        "event_id": event,
                        **identity,
                        "state": "DELETED",
                        "reason": "RETENTION_EXPIRED",
                    }
                )
            cursor = await self._execute(
                "SELECT tenant_id,task_id FROM {schema}.memory_query_operations WHERE "
                + condition
                + "expires_at<=%s AND (embedding IS NOT NULL OR item_refs<>'[]') ORDER BY expires_at,task_id LIMIT %s FOR UPDATE SKIP LOCKED",
                (*scope_params, now, limit),
            )
            query_rows = cursor.fetchall()
            query_rows = tuple(
                await query_rows if inspect.isawaitable(query_rows) else query_rows
            )
            for tenant, task in query_rows:
                await self._execute(
                    "UPDATE {schema}.memory_query_operations SET embedding=NULL,item_refs='[]',state=CASE WHEN state IN ('INFLIGHT','UNKNOWN') THEN state ELSE 'DELETED' END WHERE tenant_id=%s AND task_id=%s",
                    (tenant, task),
                )
            entries_left = await self._one(
                "SELECT 1 FROM {schema}.memory_index_entries WHERE "
                + condition
                + "expires_at<=%s LIMIT 1",
                (*scope_params, now),
            )
            queries_left = await self._one(
                "SELECT 1 FROM {schema}.memory_query_operations WHERE "
                + condition
                + "expires_at<=%s AND (embedding IS NOT NULL OR item_refs<>'[]') LIMIT 1",
                (*scope_params, now),
            )
        return {
            "scope_key": scope.key if scope is not None else None,
            "index_receipts": receipts,
            "query_scrubbed": len(query_rows),
            "remaining": bool(entries_left or queries_left),
        }

    async def query_retention(self, request) -> int:
        allowed = request.allowed
        if not allowed or len(allowed) > 10000:
            raise ValueError("MEMORY_QUERY_INDEX_REQUIRED")
        values = ",".join("(%s,%s,%s,%s,%s)" for _ in allowed)
        params = tuple(
            value
            for identity in allowed
            for value in (
                identity.item_id,
                identity.version_id,
                identity.generation,
                identity.deletion_epoch,
                identity.source_fingerprint,
            )
        )
        rows = await self._read(
            "WITH allowed(item_id,version_id,generation,deletion_epoch,source_fingerprint) AS (VALUES "
            + values
            + ") "
            "SELECT MIN(e.expires_at) FROM {schema}.memory_index_entries e JOIN allowed a ON e.item_id=a.item_id AND e.version_id=a.version_id AND e.generation=a.generation AND e.deletion_epoch=a.deletion_epoch AND e.source_fingerprint=a.source_fingerprint JOIN {schema}.memory_index_fences f ON f.scope_key=e.scope_key AND f.item_id=e.item_id AND f.generation=e.generation AND f.deletion_epoch=e.deletion_epoch AND f.deleted=FALSE WHERE e.scope_key=%s AND e.embedding_model=%s AND e.dimension=%s AND e.policy_version=%s AND e.expires_at>%s",
            (
                *params,
                request.scope.key,
                request.space.embedding_model,
                request.space.dimension,
                request.space.policy_version,
                int(time.time()),
            ),
        )
        row = rows[0] if rows else None
        if not row or row[0] is None:
            raise ValueError("MEMORY_QUERY_INDEX_REQUIRED")
        return min(request.expires_at, int(row[0]))

    async def claim_query(
        self,
        request,
        query_hash: str,
        *,
        preview: bool = False,
        expires_at: int | None = None,
    ) -> QueryEmbeddingLease | None:
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "scope": request.scope.key,
                    "space": asdict(request.space),
                    "query_hash": query_hash,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        tenant, task = request.scope.tenant_id, request.execution.task_id
        operation = (
            "memory-query-"
            + hashlib.sha256((tenant + "\0" + task).encode()).hexdigest()
        )
        expired = False
        async with self._transaction():
            row = await self._one(
                "SELECT fingerprint,token,state,operation_id,embedding,expires_at FROM {schema}.memory_query_operations WHERE tenant_id=%s AND task_id=%s FOR UPDATE",
                (tenant, task),
            )
            if row and int(time.time()) >= row[5]:
                await self._execute(
                    "UPDATE {schema}.memory_query_operations SET embedding=NULL,item_refs='[]',state=CASE WHEN state IN ('INFLIGHT','UNKNOWN') THEN state ELSE 'DELETED' END WHERE tenant_id=%s AND task_id=%s",
                    (tenant, task),
                )
                expired = True
            elif row:
                if row[0] != fingerprint:
                    raise ValueError("MEMORY_QUERY_TASK_OPPORTUNITY_USED")
                if row[2] == "READY" and row[4] is not None:
                    vector = tuple(json.loads(row[4]))
                    validate_memory_vector(vector, request.space)
                    return QueryEmbeddingLease(row[1], row[3], fingerprint, vector)
                raise ValueError("MEMORY_QUERY_OPERATION_UNRESOLVED")
            elif preview:
                return None
            else:
                deadline = (
                    request.expires_at
                    if expires_at is None
                    else min(request.expires_at, expires_at)
                )
                if type(deadline) is not int or deadline <= time.time():
                    raise ValueError("MEMORY_QUERY_RETENTION_EXPIRED")
                token = uuid.uuid4().hex
                refs = json.dumps(
                    [asdict(identity) for identity in request.allowed],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                inserted = await self._one(
                    "INSERT INTO {schema}.memory_query_operations(tenant_id,task_id,scope_key,embedding_model,dimension,policy_version,query_hash,fingerprint,token,state,operation_id,embedding,item_refs,created_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'INFLIGHT',%s,NULL,%s,%s,%s) ON CONFLICT(tenant_id,task_id) DO NOTHING RETURNING token",
                    (
                        tenant,
                        task,
                        request.scope.key,
                        request.space.embedding_model,
                        request.space.dimension,
                        request.space.policy_version,
                        query_hash,
                        fingerprint,
                        token,
                        operation,
                        refs,
                        int(time.time()),
                        deadline,
                    ),
                )
                if inserted is None:
                    raise ValueError("MEMORY_QUERY_OPERATION_UNRESOLVED")
                return QueryEmbeddingLease(token, operation, fingerprint)
        if expired:
            raise ValueError("MEMORY_QUERY_RETENTION_EXPIRED")
        return None

    async def complete_query(
        self,
        lease: QueryEmbeddingLease,
        vector: tuple[float, ...],
        space: MemoryIndexSpace,
    ) -> None:
        validate_memory_vector(vector, space)
        async with self._transaction():
            changed = await self._one(
                "UPDATE {schema}.memory_query_operations SET state='READY',embedding=%s WHERE token=%s AND fingerprint=%s AND state='INFLIGHT' AND expires_at>%s RETURNING token",
                (json.dumps(vector), lease.token, lease.fingerprint, int(time.time())),
            )
            if changed is None:
                raise ValueError("MEMORY_QUERY_LEASE_CONFLICT")

    async def fail_query_unknown(self, lease: QueryEmbeddingLease) -> None:
        async with self._transaction():
            await self._execute(
                "UPDATE {schema}.memory_query_operations SET state='UNKNOWN' WHERE token=%s AND state='INFLIGHT'",
                (lease.token,),
            )

    def __init__(self, provider: PostgresProvider):
        if type(provider) is not PostgresProvider:
            raise ValueError("MEMORY_INDEX_POSTGRES_PROVIDER_REQUIRED")
        self.provider = provider
        self._lock = asyncio.Lock()

    async def _execute(self, sql, params=()):
        result = self.provider.connection.execute(
            sql.replace("{schema}", self.provider.schema), params
        )
        return await result if inspect.isawaitable(result) else result

    async def _read(self, sql, params=()):
        async with self._lock:
            cursor = await self._execute(sql, params)
            rows = cursor.fetchall()
            return tuple(await rows if inspect.isawaitable(rows) else rows)

    async def _one(self, sql, params=()):
        cursor = await self._execute(sql, params)
        result = cursor.fetchone()
        return await result if inspect.isawaitable(result) else result

    @asynccontextmanager
    async def _transaction(self):
        async with self._lock:
            connection = self.provider.connection
            if hasattr(connection, "info") and (
                not connection.autocommit
                or connection.info.transaction_status != TransactionStatus.IDLE
                or connection.info.pipeline_status != PipelineStatus.OFF
            ):
                raise ValueError("MEMORY_INDEX_DEDICATED_IDLE_CONNECTION_REQUIRED")
            async with connection.transaction():
                yield

    @staticmethod
    def _key(request):
        return (
            request.scope.key,
            request.space.embedding_model,
            request.space.dimension,
            request.space.policy_version,
            request.identity.item_id,
        )

    async def _fence(self, scope, item_id):
        scope_key = scope if isinstance(scope, str) else scope.key
        await self._execute(
            "INSERT INTO {schema}.memory_index_fences(scope_key,item_id,generation,deletion_epoch,deleted,forget_epoch) VALUES(%s,%s,0,0,FALSE,-1) ON CONFLICT(scope_key,item_id) DO NOTHING",
            (scope_key, item_id),
        )
        return await self._one(
            "SELECT generation,deletion_epoch,deleted,forget_epoch FROM {schema}.memory_index_fences WHERE scope_key=%s AND item_id=%s FOR UPDATE",
            (scope_key, item_id),
        )

    async def claim(self, request: IndexUpsert) -> IndexLease:
        if type(request) is not IndexUpsert or time.time() >= request.expires_at:
            raise ValueError("MEMORY_INDEX_AUTHORIZATION_EXPIRED")
        fingerprint = index_fingerprint(request)
        key = self._key(request)
        identity = request.identity
        operation = (
            "memory-index-"
            + hashlib.sha256(
                (request.scope.tenant_id + "\0" + request.execution.task_id).encode()
            ).hexdigest()
        )
        async with self._transaction():
            fence = await self._fence(request.scope, identity.item_id)
            if (
                identity.generation < fence[0]
                or identity.deletion_epoch < fence[1]
                or identity.deletion_epoch <= fence[3]
                or (
                    fence[2]
                    and identity.generation <= fence[0]
                    and identity.deletion_epoch <= fence[1]
                )
            ):
                raise ValueError("MEMORY_INDEX_STALE_OR_DELETED")
            prior = await self._one(
                "SELECT fingerprint,token,state,operation_id FROM {schema}.memory_index_jobs WHERE scope_key=%s AND embedding_model=%s AND dimension=%s AND policy_version=%s AND item_id=%s AND generation=%s FOR UPDATE",
                (*key, identity.generation),
            )
            if prior:
                if prior[0] != fingerprint:
                    raise ValueError("MEMORY_INDEX_GENERATION_CONFLICT")
                if prior[2] == "READY":
                    return IndexLease(request, prior[1], prior[3], fingerprint, True)
                raise ValueError("MEMORY_INDEX_OPERATION_UNRESOLVED")
            slot = await self._one(
                "INSERT INTO {schema}.memory_index_task_slots(tenant_id,task_id,operation_id,fingerprint) VALUES(%s,%s,%s,%s) ON CONFLICT(tenant_id,task_id) DO NOTHING RETURNING operation_id",
                (
                    request.scope.tenant_id,
                    request.execution.task_id,
                    operation,
                    fingerprint,
                ),
            )
            if slot is None:
                raise ValueError("MEMORY_INDEX_TASK_OPPORTUNITY_USED")
            token = uuid.uuid4().hex
            await self._execute(
                "INSERT INTO {schema}.memory_index_jobs(scope_key,embedding_model,dimension,policy_version,item_id,generation,version_id,deletion_epoch,source_fingerprint,fingerprint,token,state,operation_id,event_id,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'INFLIGHT',%s,%s,%s)",
                (
                    *key,
                    identity.generation,
                    identity.version_id,
                    identity.deletion_epoch,
                    identity.source_fingerprint,
                    fingerprint,
                    token,
                    operation,
                    request.event_id,
                    int(time.time()),
                ),
            )
            await self._execute(
                "UPDATE {schema}.memory_index_fences SET generation=%s,deletion_epoch=%s,deleted=FALSE WHERE scope_key=%s AND item_id=%s",
                (
                    identity.generation,
                    identity.deletion_epoch,
                    request.scope.key,
                    identity.item_id,
                ),
            )
            # 新generation在向量尚未就绪时也不回退旧投影。
            await self._execute(
                "DELETE FROM {schema}.memory_index_entries WHERE scope_key=%s AND item_id=%s AND generation<%s",
                (request.scope.key, identity.item_id, identity.generation),
            )
            return IndexLease(request, token, operation, fingerprint)

    async def complete(self, lease: IndexLease, vector: tuple[float, ...]) -> None:
        request, identity = lease.request, lease.request.identity
        if time.time() >= request.retention_expires_at:
            raise ValueError("MEMORY_INDEX_RETENTION_EXPIRED")
        validate_memory_vector(vector, request.space)
        async with self._transaction():
            fence = await self._fence(request.scope, identity.item_id)
            if (
                fence[2]
                or fence[0] != identity.generation
                or fence[1] != identity.deletion_epoch
            ):
                raise ValueError("MEMORY_INDEX_STALE_OR_DELETED")
            job = await self._one(
                "SELECT state,fingerprint,token FROM {schema}.memory_index_jobs WHERE scope_key=%s AND embedding_model=%s AND dimension=%s AND policy_version=%s AND item_id=%s AND generation=%s FOR UPDATE",
                (*self._key(request), identity.generation),
            )
            if job != ("INFLIGHT", lease.fingerprint, lease.token):
                raise ValueError("MEMORY_INDEX_LEASE_CONFLICT")
            await self._execute(
                "INSERT INTO {schema}.memory_index_entries(scope_key,embedding_model,dimension,policy_version,item_id,generation,version_id,deletion_epoch,source_fingerprint,embedding,terms,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(scope_key,embedding_model,dimension,policy_version,item_id) DO UPDATE SET generation=EXCLUDED.generation,version_id=EXCLUDED.version_id,deletion_epoch=EXCLUDED.deletion_epoch,source_fingerprint=EXCLUDED.source_fingerprint,embedding=EXCLUDED.embedding,terms=EXCLUDED.terms,expires_at=EXCLUDED.expires_at WHERE memory_index_entries.generation<=EXCLUDED.generation",
                (
                    *self._key(request),
                    identity.generation,
                    identity.version_id,
                    identity.deletion_epoch,
                    identity.source_fingerprint,
                    json.dumps(vector),
                    json.dumps(request.terms, ensure_ascii=False),
                    request.retention_expires_at,
                ),
            )
            await self._execute(
                "UPDATE {schema}.memory_index_jobs SET state='READY' WHERE token=%s AND state='INFLIGHT'",
                (lease.token,),
            )

    async def fail_unknown(self, lease: IndexLease) -> None:
        async with self._transaction():
            await self._execute(
                "UPDATE {schema}.memory_index_jobs SET state='UNKNOWN' WHERE token=%s AND state='INFLIGHT'",
                (lease.token,),
            )

    async def delete(self, request: IndexDelete) -> None:
        async with self._transaction():
            fence = await self._fence(request.scope, request.item_id)
            if request.deletion_epoch < fence[1]:
                return
            advances_epoch = request.deletion_epoch > fence[1]
            current_target = advances_epoch or request.generation >= fence[0]
            if current_target:
                await self._execute(
                    "UPDATE {schema}.memory_index_fences SET generation=%s,deletion_epoch=%s,deleted=TRUE,forget_epoch=%s WHERE scope_key=%s AND item_id=%s",
                    (
                        max(fence[0], request.generation),
                        request.deletion_epoch,
                        request.deletion_epoch if advances_epoch else fence[3],
                        request.scope.key,
                        request.item_id,
                    ),
                )
            await self._execute(
                "DELETE FROM {schema}.memory_index_entries WHERE scope_key=%s AND item_id=%s AND (deletion_epoch<%s OR (deletion_epoch=%s AND generation<=%s))",
                (
                    request.scope.key,
                    request.item_id,
                    request.deletion_epoch,
                    request.deletion_epoch,
                    request.generation,
                ),
            )
            await self._execute(
                "UPDATE {schema}.memory_index_jobs SET state='DELETED' WHERE scope_key=%s AND item_id=%s AND (deletion_epoch<%s OR (deletion_epoch=%s AND generation<=%s))",
                (
                    request.scope.key,
                    request.item_id,
                    request.deletion_epoch,
                    request.deletion_epoch,
                    request.generation,
                ),
            )
            if current_target:
                await self._execute(
                    "UPDATE {schema}.memory_query_operations SET state=CASE WHEN state IN ('INFLIGHT','UNKNOWN') THEN state ELSE 'DELETED' END,embedding=NULL,item_refs='[]' WHERE scope_key=%s",
                    (request.scope.key,),
                )

    async def pending_operations(self, *, now: int, limit: int = 100) -> tuple:
        if type(now) is not int or not 1 <= limit <= 100:
            raise ValueError("MEMORY_INDEX_PENDING_QUERY_INVALID")
        rows = await self._read(
            "SELECT scope_key,item_id,generation,state,created_at FROM {schema}.memory_index_jobs WHERE state IN ('INFLIGHT','UNKNOWN') AND created_at<=%s ORDER BY created_at LIMIT %s",
            (now - 86400, limit),
        )
        return rows

    async def search(
        self,
        scope: MemoryIndexScope,
        space: MemoryIndexSpace,
        allowed: tuple[MemoryIndexIdentity, ...],
        *,
        vector: tuple[float, ...] | None,
        terms: tuple[str, ...],
        limit: int,
    ) -> tuple[tuple[MemoryRecallCandidate, ...], tuple[MemoryRecallCandidate, ...]]:
        if (
            type(allowed) is not tuple
            or any(type(identity) is not MemoryIndexIdentity for identity in allowed)
            or len(allowed) > 10000
            or len({i.item_id for i in allowed}) != len(allowed)
            or type(limit) is not int
            or not 1 <= limit <= 30
            or type(terms) is not tuple
            or len(terms) > 32
            or any(
                type(term) is not str or not term.strip() or len(term) > 128
                for term in terms
            )
        ):
            raise ValueError("MEMORY_INDEX_SEARCH_BOUNDS_INVALID")
        if vector is not None:
            validate_memory_vector(vector, space)
        if not allowed:
            return (), ()
        # 每一SQL候选先JOIN完整合法身份，最多10000；不先全库相似检索再过滤。
        values = ",".join("(%s,%s,%s,%s,%s)" for _ in allowed)
        params = tuple(
            value
            for i in allowed
            for value in (
                i.item_id,
                i.version_id,
                i.generation,
                i.deletion_epoch,
                i.source_fingerprint,
            )
        )
        rows = await self._read(
            "WITH allowed(item_id,version_id,generation,deletion_epoch,source_fingerprint) AS (VALUES "
            + values
            + ") "
            "SELECT e.item_id,e.version_id,e.generation,e.deletion_epoch,e.source_fingerprint,e.embedding,e.terms FROM {schema}.memory_index_entries e JOIN allowed a ON e.item_id=a.item_id AND e.version_id=a.version_id AND e.generation=a.generation AND e.deletion_epoch=a.deletion_epoch AND e.source_fingerprint=a.source_fingerprint JOIN {schema}.memory_index_fences f ON f.scope_key=e.scope_key AND f.item_id=e.item_id AND f.generation=e.generation AND f.deletion_epoch=e.deletion_epoch AND f.deleted=FALSE WHERE e.scope_key=%s AND e.embedding_model=%s AND e.dimension=%s AND e.policy_version=%s AND e.expires_at>%s LIMIT 10001",
            (
                *params,
                scope.key,
                space.embedding_model,
                space.dimension,
                space.policy_version,
                int(time.time()),
            ),
        )
        if len(rows) > 10000:
            raise ValueError("MEMORY_INDEX_LEGAL_SET_TOO_LARGE")
        vector_results, lexical_results = [], []
        allowed_set = frozenset(allowed)
        for row in rows:
            identity = MemoryIndexIdentity(*row[:5])
            if identity not in allowed_set:
                raise ValueError("MEMORY_INDEX_FILTER_VIOLATION")
            stored_vector = tuple(json.loads(row[5]))
            stored_terms = tuple(json.loads(row[6]))
            validate_memory_vector(stored_vector, space)
            if vector is not None:
                norm = math.sqrt(sum(v * v for v in vector)) * math.sqrt(
                    sum(v * v for v in stored_vector)
                )
                score = sum(a * b for a, b in zip(vector, stored_vector)) / norm
                vector_results.append(MemoryRecallCandidate(identity, score))
            overlap = len(set(terms) & set(stored_terms))
            if overlap:
                lexical_results.append(MemoryRecallCandidate(identity, float(overlap)))
        order = lambda item: (-item.score, item.identity.item_id)
        return tuple(sorted(vector_results, key=order)[:limit]), tuple(
            sorted(lexical_results, key=order)[:limit]
        )
