"""原运行活frame内的索引/词法召回；HTTP不能新建运行或付费授权。"""

import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import asdict, dataclass
from typing import Any
from weakref import ReferenceType, ref

from psycopg import Error as PostgresError
from sqlalchemy import text

from efficiency_platform_agent.core.execution_control import (
    RunControl,
    current_run_control,
    execution_scope,
)
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    bind_run_context,
    current_run_context,
)
from efficiency_platform_agent.memory.indexing import (
    GuardedMemoryIndexEmbedding,
    GuardedMemoryQueryEmbedding,
    MemoryIndexingService,
)
from efficiency_platform_agent.memory.recall import MemoryRecallService


def source_fingerprint(dependencies) -> str:
    values = sorted(
        (asdict(dep) for dep in set(dependencies)),
        key=lambda item: (
            item["source_type"],
            item["source_id"],
            item["source_version"],
            item["grant_epoch"],
            item["source_epoch"],
            item["deletion_epoch"],
        ),
    )
    return hashlib.sha256(
        json.dumps(
            values, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


@dataclass
class _Frame:
    binding: RunContextBinding
    control: ReferenceType[RunControl]
    task: ReferenceType[asyncio.Task[Any]]
    active: bool = True


class MemoryIndexRuntime:
    def __init__(
        self,
        index,
        execution_store,
        send_authority,
        ledger,
        embedding_provider,
        *,
        index_enabled=False,
        recall_enabled=False,
        query_embedding_enabled=False,
    ):
        self.index, self.store, self.send_authority, self.ledger = (
            index,
            execution_store,
            send_authority,
            ledger,
        )
        self.index_enabled, self.recall_enabled = index_enabled, recall_enabled
        self.expiry_worker = MemoryIndexExpiryWorker(index)
        self.query_embedding_enabled = query_embedding_enabled
        self.frames = {}
        embedding = GuardedMemoryIndexEmbedding(embedding_provider, ledger, self)
        self.indexing = MemoryIndexingService(
            index, self, embedding, enabled=index_enabled
        )
        query_embedding = (
            GuardedMemoryQueryEmbedding(embedding_provider, ledger, self, index)
            if query_embedding_enabled
            else None
        )
        self.recalling = MemoryRecallService(
            index, self, query_embedding, enabled=recall_enabled
        )

    @contextmanager
    def for_run(self):
        binding, control, task = (
            current_run_context(),
            current_run_control(),
            asyncio.current_task(),
        )
        if (
            binding is None
            or binding.memory_context is None
            or control is None
            or task is None
        ):
            raise PermissionError("MEMORY_INDEX_ORIGINAL_FRAME_REQUIRED")
        control.check()
        self.ledger.bind_execution(
            binding.conversation.tenant_id,
            binding.execution_id,
            min(
                600000,
                max(1, int(binding.deadline_epoch_seconds * 1000 - time.time() * 1000)),
            ),
            context_scope=binding.conversation,
        )
        key = binding.conversation.tenant_id, binding.execution_id
        if key in self.frames:
            raise PermissionError("MEMORY_INDEX_FRAME_CONFLICT")
        frame = _Frame(binding, ref(control), ref(task))
        self.frames[key] = frame
        try:
            yield
        finally:
            frame.active = False
            self.frames.pop(key, None)

    def _frame(self, execution):
        frame = self.frames.get(
            (execution.conversation.tenant_id, execution.execution_id)
        )
        if frame is None or not frame.active:
            raise PermissionError("MEMORY_INDEX_ORIGINAL_FRAME_REQUIRED")
        control, task = frame.control(), frame.task()
        binding = frame.binding
        if (
            control is None
            or task is None
            or task.done()
            or task.cancelling()
            or (binding.conversation, binding.task_id, binding.execution_id)
            != (execution.conversation, execution.task_id, execution.execution_id)
        ):
            raise PermissionError("MEMORY_INDEX_ORIGINAL_FRAME_REQUIRED")
        control.check()
        return frame, binding, control

    async def _check(self, scope, space, execution, identities, expiry):
        _, binding, control = self._frame(execution)
        record = await self.store.get(scope.tenant_id, execution.execution_id)
        if (
            record is None
            or record.state != "ACTIVE"
            or record.context != binding.memory_context
            or time.time()
            >= min(
                expiry, record.deadline_epoch_seconds, record.context.packet.expires_at
            )
            or expiry > record.deadline_epoch_seconds
            or space.policy_version != record.context.policy.version
            or scope.scope_kind != "USER_PRIVATE"
            or scope.key
            != type(scope)(
                scope.tenant_id, scope.user_id, scope.domain, scope.top_level_agent_id
            ).key
            or (scope.tenant_id, scope.user_id, scope.domain, scope.top_level_agent_id)
            != (
                binding.conversation.tenant_id,
                binding.conversation.user_id,
                binding.conversation.domain,
                binding.conversation.top_level_agent_id,
            )
        ):
            raise PermissionError("MEMORY_INDEX_AUTHORITY_DENIED")
        packet = record.context.packet
        if (
            any(
                (grant.node_id, grant.execution_agent_id, grant.purpose)
                == (
                    execution.subtask_id,
                    execution.execution_agent_id,
                    execution.purpose,
                )
                for grant in record.context.execution_grants
            )
            is not True
        ):
            raise PermissionError("MEMORY_INDEX_EXECUTION_GRANT_DENIED")
        for identity in identities:
            item = next(
                (
                    item
                    for item in packet.items
                    if (item.item_id, item.version)
                    == (identity.item_id, identity.version_id)
                ),
                None,
            )
            if (
                item is None
                or identity.source_fingerprint
                != source_fingerprint(item.safety_dependencies)
                or identity.deletion_epoch
                != max(
                    (dep.deletion_epoch for dep in item.safety_dependencies), default=0
                )
            ):
                raise PermissionError("MEMORY_INDEX_ITEM_AUTHORITY_DENIED")
            if not await self.send_authority.registry.source_authority.current(
                execution, item.safety_dependencies
            ):
                raise PermissionError("MEMORY_INDEX_SOURCE_DENIED")
        control.check()
        return record

    async def check_upsert(self, request):
        if (
            type(request.retention_expires_at) is not int
            or request.retention_expires_at < request.expires_at
            or time.time() >= request.retention_expires_at
        ):
            raise PermissionError("MEMORY_INDEX_RETENTION_INVALID")
        await self._check(
            request.scope,
            request.space,
            request.execution,
            (request.identity,),
            request.expires_at,
        )
        record = await self.store.get(
            request.scope.tenant_id, request.execution.execution_id
        )
        item = next(
            item
            for item in record.context.packet.items
            if item.item_id == request.identity.item_id
        )
        if request.projection != item.value or any(
            term not in item.value for term in request.terms
        ):
            raise PermissionError("MEMORY_INDEX_PROJECTION_AUTHORITY_DENIED")
        self.ledger.check_execution(
            request.scope.tenant_id, request.execution.execution_id
        )

    async def check(self, request):
        if request.query_embedding_allowed and not self.query_embedding_enabled:
            raise PermissionError("MEMORY_QUERY_EMBEDDING_NOT_AUTHORIZED")
        await self._check(
            request.scope,
            request.space,
            request.execution,
            request.allowed,
            request.expires_at,
        )
        if request.query_embedding_allowed:
            record = await self.store.get(
                request.scope.tenant_id, request.execution.execution_id
            )
            if record is None or record.context.policy.max_paid_operations < 1:
                raise PermissionError("MEMORY_QUERY_EMBEDDING_NOT_AUTHORIZED")
            self.ledger.check_execution(
                request.scope.tenant_id, request.execution.execution_id
            )

    async def check_delete(self, request):
        # 该方法仅由已通过Java内部Bearer/Xtenant认证的delete路由调用；不需要活运行或预算。
        return None

    @asynccontextmanager
    async def _bound(self, execution):
        frame, binding, control = self._frame(execution)
        with bind_run_context(binding), execution_scope(control):
            # 固定PG→MySQL锁顺序，锁保持至Embedding及READY提交完成。
            async with self.send_authority.acquire():
                async with (
                    self.send_authority.execution_store.engine.begin() as connection
                ):
                    row = (
                        await connection.execute(
                            text(
                                "SELECT state FROM agent_memory_execution WHERE tenant_id=:tenant AND execution_id=:execution FOR UPDATE"
                            ),
                            {
                                "tenant": execution.conversation.tenant_id.encode(),
                                "execution": execution.execution_id.encode(),
                            },
                        )
                    ).first()
                    if row is None or row[0] != "ACTIVE" or not frame.active:
                        raise PermissionError("MEMORY_ACCESS_REVOKED")
                    yield

    async def upsert(self, request):
        async with self._bound(request.execution):
            state = await self.indexing.upsert(request)
        return self._receipt(request, state)

    async def delete(self, request):
        await self.indexing.delete(request)
        return self._receipt(request, "DELETED")

    async def expire(self, scope, *, limit=100):
        return await self.index.expire(scope, now=int(time.time()), limit=limit)

    async def recall(self, request, *, terms=(), query=None):
        if (
            query is not None or request.query_embedding_allowed
        ) and not self.query_embedding_enabled:
            raise PermissionError("MEMORY_QUERY_EMBEDDING_NOT_AUTHORIZED")
        async with self._bound(request.execution):
            return await self.recalling.recall(request, terms=terms, query=query)

    @staticmethod
    def _receipt(request, state):
        identity = getattr(request, "identity", None)
        return {
            "event_id": request.event_id,
            "scope_key": request.scope.key,
            "item_id": identity.item_id if identity else request.item_id,
            "version_id": identity.version_id if identity else None,
            "generation": identity.generation if identity else request.generation,
            "deletion_epoch": identity.deletion_epoch
            if identity
            else request.deletion_epoch,
            "state": state,
        }


class MemoryIndexCleanupRuntime:
    """显式配置的历史索引CPU清理，不需要模型、活运行或费用账本。"""

    def __init__(self, index):
        self.index = index
        self.expiry_worker = MemoryIndexExpiryWorker(index)

    async def delete(self, request):
        await self.index.delete(request)
        return MemoryIndexRuntime._receipt(request, "DELETED")

    async def expire(self, scope, *, limit=100):
        return await self.index.expire(scope, now=int(time.time()), limit=limit)

    async def upsert(self, request):
        raise ValueError("MEMORY_INDEX_FEATURE_DISABLED")

    async def recall(self, request, **kwargs):
        raise ValueError("MEMORY_RECALL_FEATURE_DISABLED")


class MemoryIndexExpiryWorker:
    """已装配backend的有界CPU擦除；全自有schema按截止推进，不依赖后续HTTP请求。"""

    def __init__(self, index, *, interval_seconds=30):
        self.index = index
        self.interval = interval_seconds
        self.task = None
        self.last_result = None
        self.last_error = False
        self.completed = asyncio.Event()

    async def start(self):
        if self.task is None:
            self.task = asyncio.create_task(self._run())

    async def _run(self):
        while True:
            try:
                self.last_result = await self.index.expire(
                    None, now=int(time.time()), limit=100
                )
                self.last_error = False
            except (PostgresError, RuntimeError, ValueError, OSError):
                # 不记录DB异常/绑定正文；失败留原墓碑与未决状态，下个CPU批次复试。
                self.last_error = True
            self.completed.set()
            await asyncio.sleep(self.interval)

    async def close(self):
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
