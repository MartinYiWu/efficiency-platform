"""专属PostgreSQL技术登记簿；持久行锁覆盖正常Saver操作，保留撤销墓碑。"""

import asyncio
import hashlib
import json
import re
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from psycopg import AsyncConnection, sql
from psycopg.pq import PipelineStatus, TransactionStatus
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from efficiency_platform_agent.core.checkpoint_erasure import (
    ThreadBinding,
    ThreadErasurePlan,
    Verification,
)
from efficiency_platform_agent.core.memory import (
    ConversationScope,
    ExecutionScope,
    SourceDependency,
)
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionStore,
    memory_operation_deadline_matches,
)
from efficiency_platform_agent.core.memory_thread import (
    CheckpointLocation,
    ResumeReceipt,
    ResumeRequest,
    SourceEpochAuthority,
    ThreadBackendInventory,
    ThreadCleanupReceipt,
)


def _scope(value: dict[str, Any]) -> ExecutionScope:
    return ExecutionScope(
        **(value | {"conversation": ConversationScope(**value["conversation"])})
    )


def _dependencies(value: list[dict[str, Any]]) -> tuple[SourceDependency, ...]:
    return tuple(SourceDependency(**item) for item in value)


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def _receipt_key(record_type: str, request_id: str) -> str:
    return json.dumps(
        ["memory-thread-receipt/2", record_type, request_id],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _erasure_event(receipt_key: str) -> str | None:
    try:
        value = json.loads(receipt_key)
        if (
            isinstance(value, list)
            and len(value) == 3
            and value[:2] == ["memory-thread-receipt/2", "ERASURE"]
            and isinstance(value[2], str)
            and value[2]
            and _receipt_key("ERASURE", value[2]) == receipt_key
        ):
            return value[2]
    except (ValueError, TypeError):
        pass
    return None


class PostgresMemoryExecutionRegistry:
    requires_encrypted_checkpoints = True

    def __init__(
        self,
        connection: AsyncConnection[Any],
        schema: str,
        execution_store: MemoryExecutionStore,
        source_authority: SourceEpochAuthority,
        inventories: tuple[ThreadBackendInventory, ...],
        *,
        clock: Callable[[], float] = time.time,
        checkpoint_capability: str = "GRAPH",
    ):
        if not isinstance(connection, AsyncConnection) or not re.fullmatch(
            r"(?:agent_runtime|memory_it)_[a-z0-9_]+", schema
        ):
            raise ValueError("MEMORY_REGISTRY_CONFIGURATION_INVALID")
        ids = tuple(item.backend_id for item in inventories)
        if (
            len(set(ids)) != len(ids)
            or checkpoint_capability not in {"GRAPH", "NONE_ONLY"}
            or (checkpoint_capability == "GRAPH" and not ids)
            or (checkpoint_capability == "NONE_ONLY" and ids)
        ):
            raise ValueError("MEMORY_BACKEND_INVENTORY_REQUIRED")
        self.checkpoint_capability = checkpoint_capability
        self.connection, self.schema = connection, schema
        self.connection.row_factory = dict_row
        self.execution_store, self.source_authority = execution_store, source_authority
        self.inventories, self.backend_ids, self.clock = (
            inventories,
            frozenset(ids),
            clock,
        )
        self._lock = asyncio.Lock()
        self._result_authority = None
        self._wait_authority = None
        self._wait_checkpoint_context: ContextVar[Any] = ContextVar(
            "memory_wait_checkpoint_scope", default=None
        )
        self._result_checkpoint_context: ContextVar[Any] = ContextVar(
            "memory_result_checkpoint_scope", default=None
        )

    def install_result_authority(self, authority) -> None:
        if self._result_authority is not None or not callable(
            getattr(authority, "validate_issued", None)
        ):
            raise ValueError("MEMORY_RESULT_AUTHORITY_ALREADY_CONFIGURED")
        self._result_authority = authority

    def install_wait_authority(self, authority) -> None:
        if self._wait_authority is not None or not callable(
            getattr(authority, "validate_wait_capability", None)
        ):
            raise ValueError("MEMORY_WAIT_AUTHORITY_ALREADY_CONFIGURED")
        self._wait_authority = authority

    def current_wait_checkpoint_capability(self):
        current = self._wait_checkpoint_context.get()
        if current is None:
            return None
        capability, _ = current
        if (
            self._wait_authority is None
            or self._wait_authority.validate_wait_capability(capability) is not True
        ):
            raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        return capability

    @asynccontextmanager
    async def wait_checkpoint_scope(self, capability):
        from efficiency_platform_agent.core.memory_execution import (
            MemoryWaitCheckpointCapability,
            bind_memory_wait_checkpoint_capability,
        )

        if (
            not isinstance(capability, MemoryWaitCheckpointCapability)
            or self._wait_authority is None
            or self._wait_authority.validate_wait_capability(capability) is not True
            or self._wait_authority.validate_wait_scope_task(capability) is not True
            or self._wait_checkpoint_context.get() is not None
        ):
            raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        key = (capability.scope.conversation.tenant_id, capability.scope.execution_id)
        async with self._transaction():
            row = await self._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                key,
            )
            if (
                row is None
                or row["checkpoint_mode"] != "GRAPH"
                or row["state"] != "WAITING_CONTEXT"
                or row["wait_status"] != "BUILDING"
                or row["wait_event_id"] != capability.wait_event_id
                or _scope(row["scope"]) != capability.scope
                or row["runtime_id"] != capability.runtime_id
                or row["execution_revision"] != capability.execution_revision
                or row["packet_revision"] != capability.packet_revision
                or row["wait_context_fingerprint"]
                != capability.current_context_fingerprint
                or row["original_deadline"] != capability.original_deadline
            ):
                raise PermissionError("MEMORY_WAIT_CONSUMED")
            denial = await self._active(
                row | {"state": "ACTIVE"}, ignore_packet_ttl=True
            )
            if denial:
                raise PermissionError(denial)
            token = self._wait_checkpoint_context.set((capability, row))
            try:
                with bind_memory_wait_checkpoint_capability(capability):
                    yield capability
            finally:
                self._wait_checkpoint_context.reset(token)

    def _sql(self, template: str):
        return sql.SQL(template).format(
            **{
                name: sql.Identifier(self.schema, "agent_memory_thread_" + name)
                for name in ("execution", "member", "namespace", "resume")
            }
        )

    @asynccontextmanager
    async def _transaction(self):
        async with self._lock:
            connection = self.connection
            if (
                not connection.autocommit
                or connection.info.transaction_status != TransactionStatus.IDLE
                or connection.info.pipeline_status != PipelineStatus.OFF
            ):
                raise ValueError("MEMORY_REGISTRY_DEDICATED_IDLE_CONNECTION_REQUIRED")
            async with connection.transaction():
                yield connection

    async def _one(self, template, params):
        return await (
            await self.connection.execute(self._sql(template), params)
        ).fetchone()

    async def _members(self, row):
        return await (
            await self.connection.execute(
                self._sql(
                    "SELECT * FROM {member} WHERE tenant_id=%s AND execution_id=%s ORDER BY thread_id"
                ),
                (row["tenant_id"], row["execution_id"]),
            )
        ).fetchall()

    async def _inventory_complete(self, row, members) -> bool:
        if row.get("checkpoint_mode", "GRAPH") != "GRAPH":
            return False
        if frozenset(row["backend_ids"]) != self.backend_ids:
            return False
        registered = frozenset(member["thread_id"] for member in members)
        if row["runtime_id"] != row["root_thread_id"]:
            return False
        dependencies = set(_dependencies(row["dependencies"]))
        for member in members:
            if (member["tenant_id"], member["execution_id"]) != (
                row["tenant_id"],
                row["execution_id"],
            ):
                return False
            if not set(_dependencies(member["dependencies"])).issubset(dependencies):
                return False
            if member["thread_id"] == row["root_thread_id"]:
                if member["parent_thread_id"] is not None:
                    return False
            elif (
                not member["thread_id"].startswith(row["root_thread_id"] + ":child:")
                or member["parent_thread_id"] not in registered
            ):
                return False
        for inventory in self.inventories:
            entries = await inventory.entries(row["root_thread_id"])
            if not frozenset(thread for thread, _, _ in entries).issubset(registered):
                return False
            namespaces = await (
                await self.connection.execute(
                    self._sql(
                        "SELECT n.* FROM {namespace} n JOIN {member} m USING(thread_id) WHERE m.tenant_id=%s AND m.execution_id=%s AND n.backend_id=%s"
                    ),
                    (row["tenant_id"], row["execution_id"], inventory.backend_id),
                )
            ).fetchall()
            namespace_map = {
                (item["thread_id"], item["checkpoint_ns"]): item["pending_writes"]
                for item in namespaces
            }
            if any(
                (thread, namespace) not in namespace_map
                or (pending and not namespace_map[(thread, namespace)])
                for thread, namespace, pending in entries
            ):
                return False
        return bool(registered) and row["root_thread_id"] in registered

    async def _owner_record(self, scope: ExecutionScope, runtime_id: str):
        record = await self.execution_store.get(
            scope.conversation.tenant_id, scope.execution_id
        )
        if record is None or record.state != "ACTIVE":
            raise PermissionError("MEMORY_EXECUTION_OWNER_REQUIRED")
        context, packet = record.context, record.context.packet
        if (packet.scope, packet.task_id, packet.execution_id, record.runtime_id) != (
            scope.conversation,
            scope.task_id,
            scope.execution_id,
            runtime_id,
        ) or not any(
            (grant.node_id, grant.execution_agent_id, grant.purpose)
            == (scope.subtask_id, scope.execution_agent_id, scope.purpose)
            for grant in context.execution_grants
        ):
            raise PermissionError("MEMORY_EXECUTION_OWNER_MISMATCH")
        dependencies = packet.safety_dependencies
        if not dependencies or not await self.source_authority.current(
            scope, dependencies
        ):
            raise PermissionError("MEMORY_SOURCE_AUTHORITY_DENIED")
        if int(self.clock()) >= min(record.deadline_epoch_seconds, packet.expires_at):
            raise PermissionError("MEMORY_PACKET_EXPIRED")
        return record

    async def enroll(self, scope: ExecutionScope, runtime_id: str) -> None:
        if self.checkpoint_capability != "GRAPH":
            raise PermissionError("MEMORY_CHECKPOINT_CAPABILITY_DENIED")
        record = await self._owner_record(scope, runtime_id)
        context, packet = record.context, record.context.packet
        dependencies = packet.safety_dependencies
        params = (
            scope.conversation.tenant_id,
            scope.execution_id,
            runtime_id,
            runtime_id,
            Jsonb(asdict(scope)),
            record.request_fingerprint,
            record.execution_revision,
            Jsonb([asdict(dep) for dep in dependencies]),
            Jsonb(sorted(self.backend_ids)),
            packet.packet_revision,
            packet.expires_at,
            record.deadline_epoch_seconds,
            context.semantic_snapshot_digest,
        )
        initial_fp = (
            _hash(context.metadata()) if self._wait_authority is not None else None
        )
        async with self._transaction():
            await self.connection.execute(
                self._sql(
                    "INSERT INTO {execution} (tenant_id,execution_id,runtime_id,root_thread_id,scope,operation_hash,"
                    "execution_revision,state,dependencies,backend_ids,packet_revision,packet_expires_at,original_deadline,semantic_digest"
                    + (",current_context_fingerprint" if initial_fp is not None else "")
                    + ") VALUES (%s,%s,%s,%s,%s,%s,%s,'ACTIVE',%s,%s,%s,%s,%s,%s"
                    + (",%s" if initial_fp is not None else "")
                    + ") ON CONFLICT (tenant_id,execution_id) DO NOTHING"
                ),
                (*params, initial_fp) if initial_fp is not None else params,
            )
            row = await self._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                params[:2],
            )
            if (
                row["runtime_id"] != runtime_id
                or row["scope"] != asdict(scope)
                or row["operation_hash"] != record.request_fingerprint
                or row["state"] != "ACTIVE"
                or row["execution_revision"] != record.execution_revision
                or row.get("checkpoint_mode", "GRAPH") != "GRAPH"
                or initial_fp is not None
                and row.get("current_context_fingerprint") != initial_fp
            ):
                raise PermissionError("MEMORY_THREAD_OWNER_CONFLICT")
            await self.connection.execute(
                self._sql(
                    "INSERT INTO {member} (thread_id,tenant_id,execution_id,parent_thread_id,dependencies) "
                    "VALUES (%s,%s,%s,NULL,%s) ON CONFLICT (thread_id) DO NOTHING"
                ),
                (runtime_id, *params[:2], params[7]),
            )
            members = await self._members(row)
            complete = await self._inventory_complete(row, members)
            await self.connection.execute(
                self._sql(
                    "UPDATE {execution} SET registry_complete=%s WHERE tenant_id=%s AND execution_id=%s"
                ),
                (complete, *params[:2]),
            )
        if not complete:
            raise PermissionError("MEMORY_REGISTRY_INCOMPLETE")

    async def enroll_no_checkpoint(
        self, scope: ExecutionScope, runtime_id: str
    ) -> None:
        record = await self._owner_record(scope, runtime_id)
        if (
            record.runtime_kind != "CUSTOMER_SERVICE"
            or scope.conversation.domain != "customer-service"
        ):
            raise PermissionError("MEMORY_NO_CHECKPOINT_POLICY_DENIED")
        packet = record.context.packet
        params = (
            scope.conversation.tenant_id,
            scope.execution_id,
            runtime_id,
            Jsonb(asdict(scope)),
            record.request_fingerprint,
            record.execution_revision,
            Jsonb([asdict(dep) for dep in packet.safety_dependencies]),
            packet.packet_revision,
            packet.expires_at,
            record.deadline_epoch_seconds,
            record.context.semantic_snapshot_digest,
        )
        initial_fp = (
            _hash(record.context.metadata())
            if self._wait_authority is not None
            else None
        )
        async with self._transaction():
            await self.connection.execute(
                self._sql(
                    "INSERT INTO {execution} (tenant_id,execution_id,runtime_id,root_thread_id,scope,operation_hash,execution_revision,state,dependencies,backend_ids,packet_revision,packet_expires_at,original_deadline,semantic_digest,checkpoint_mode,registry_complete"
                    + (",current_context_fingerprint" if initial_fp is not None else "")
                    + ") VALUES (%s,%s,%s,NULL,%s,%s,%s,'ACTIVE',%s,'[]'::jsonb,%s,%s,%s,%s,'NONE',true"
                    + (",%s" if initial_fp is not None else "")
                    + ") ON CONFLICT (tenant_id,execution_id) DO NOTHING"
                ),
                (*params, initial_fp) if initial_fp is not None else params,
            )
            row = await self._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                params[:2],
            )
            if (
                row["checkpoint_mode"] != "NONE"
                or row["root_thread_id"] is not None
                or row["backend_ids"]
                or row["runtime_id"] != runtime_id
                or row["scope"] != asdict(scope)
                or row["operation_hash"] != record.request_fingerprint
                or row["state"] != "ACTIVE"
                or row["execution_revision"] != record.execution_revision
                or initial_fp is not None
                and row.get("current_context_fingerprint") != initial_fp
            ):
                raise PermissionError("MEMORY_THREAD_OWNER_CONFLICT")
            complete = not await self._members(row)
            for inventory in self.inventories:
                complete = complete and not await inventory.entries(runtime_id)
            if not complete:
                await self.connection.execute(
                    self._sql(
                        "UPDATE {execution} SET state='BLOCKED',registry_complete=false,fence_revision=fence_revision+1 WHERE tenant_id=%s AND execution_id=%s"
                    ),
                    params[:2],
                )
        if not complete:
            raise PermissionError("MEMORY_REGISTRY_INCOMPLETE")

    async def _active(
        self, row, *, defer_packet_ttl=False, ignore_packet_ttl=False
    ) -> str | None:
        if row["state"] != "ACTIVE" or not row["registry_complete"]:
            return "MEMORY_THREAD_FENCED"
        scope = _scope(row["scope"])
        if (scope.conversation.tenant_id, scope.execution_id) != (
            row["tenant_id"],
            row["execution_id"],
        ):
            return "MEMORY_THREAD_OWNER_MISMATCH"
        if int(self.clock()) >= row["original_deadline"]:
            return (
                "MEMORY_EXECUTION_EXPIRED"
                if defer_packet_ttl or ignore_packet_ttl
                else "MEMORY_PACKET_EXPIRED"
            )
        if (
            not defer_packet_ttl
            and not ignore_packet_ttl
            and int(self.clock()) >= row["packet_expires_at"]
        ):
            return "MEMORY_PACKET_EXPIRED"
        if not await self.source_authority.current(
            scope, _dependencies(row["dependencies"])
        ):
            return "MEMORY_SOURCE_AUTHORITY_DENIED"
        members = await self._members(row)
        if row.get("checkpoint_mode", "GRAPH") == "NONE":
            if row["root_thread_id"] is not None or row["backend_ids"] or members:
                return "MEMORY_REGISTRY_INCOMPLETE"
            for inventory in self.inventories:
                if await inventory.entries(row["runtime_id"]):
                    return "MEMORY_REGISTRY_INCOMPLETE"
        elif not await self._inventory_complete(row, members):
            return "MEMORY_REGISTRY_INCOMPLETE"
        record = await self.execution_store.get(row["tenant_id"], row["execution_id"])
        if (
            record is None
            or record.state != "ACTIVE"
            or record.runtime_id != row["runtime_id"]
            or record.execution_revision != row["execution_revision"]
            or record.context.semantic_snapshot_digest != row["semantic_digest"]
            or record.context.packet.packet_revision != row["packet_revision"]
            or record.context.packet.expires_at != row["packet_expires_at"]
            or record.request_fingerprint != row["operation_hash"]
            or (
                record.context.packet.scope,
                record.context.packet.task_id,
                record.context.packet.execution_id,
            )
            != (scope.conversation, scope.task_id, scope.execution_id)
            or record.context.packet.safety_dependencies
            != _dependencies(row["dependencies"])
            or record.deadline_epoch_seconds != row["original_deadline"]
            or (record.grant_epoch, record.source_epoch, record.deletion_epoch)
            != (
                record.context.packet.grant_epoch,
                record.context.packet.source_epoch,
                record.context.packet.deletion_epoch,
            )
        ):
            return "MEMORY_EXECUTION_AUTHORITY_DENIED"
        if not ignore_packet_ttl and int(self.clock()) >= row["packet_expires_at"]:
            return "MEMORY_PACKET_EXPIRED"
        return None

    @asynccontextmanager
    async def send_lease_execution(
        self, tenant_id: str, execution_id: str, backend_id: str, namespace: str
    ):
        denial = None
        async with self._transaction():
            row = await self._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                (tenant_id, execution_id),
            )
            if row is None:
                raise PermissionError("MEMORY_EXECUTION_OWNER_REQUIRED")
            if (
                row.get("checkpoint_mode", "GRAPH") == "NONE"
                and (backend_id != "NO_CHECKPOINT" or namespace != "provider")
            ) or (
                row.get("checkpoint_mode", "GRAPH") == "GRAPH"
                and backend_id not in self.backend_ids
            ):
                denial = "MEMORY_CHECKPOINT_CAPABILITY_DENIED"
            elif row["state"] in {"WAITING_CONTEXT", "REFRESH_PENDING"}:
                denial = "MEMORY_REFRESH_PENDING"
            else:
                try:
                    denial = await self._active(row, defer_packet_ttl=True)
                except Exception:  # noqa: BLE001 - 权威异常不能授予发送
                    denial = "MEMORY_AUTHORITY_UNAVAILABLE"
            if denial:
                if row["state"] == "ACTIVE" and denial != "MEMORY_PACKET_EXPIRED":
                    await self.connection.execute(
                        self._sql(
                            "UPDATE {execution} SET state='BLOCKED',fence_revision=fence_revision+1 WHERE tenant_id=%s AND execution_id=%s"
                        ),
                        (tenant_id, execution_id),
                    )
            else:
                yield CheckpointLocation(
                    _scope(row["scope"]), row["runtime_id"], namespace, ()
                )
        if denial:
            raise PermissionError(denial)

    @asynccontextmanager
    async def result_lease_execution(
        self, tenant_id: str, execution_id: str, backend_id: str, namespace: str, permit
    ):
        from efficiency_platform_agent.core.memory_execution import (
            MemorySendPermit,
            bind_memory_result_checkpoint_permit,
        )

        if (
            not isinstance(permit, MemorySendPermit)
            or self._result_authority is None
            or self._result_authority.validate_issued(permit) is not True
            or (permit.scope.conversation.tenant_id, permit.scope.execution_id)
            != (tenant_id, execution_id)
        ):
            raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        async with self._transaction():
            row = await self._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                (tenant_id, execution_id),
            )
            if (
                row is None
                or (
                    _scope(row["scope"]).conversation,
                    _scope(row["scope"]).task_id,
                    _scope(row["scope"]).execution_id,
                )
                != (
                    permit.scope.conversation,
                    permit.scope.task_id,
                    permit.scope.execution_id,
                )
                or row["runtime_id"] != permit.runtime_id
                or row["execution_revision"] != permit.execution_revision
                or row["packet_revision"] != permit.packet_revision
                or not memory_operation_deadline_matches(
                    "memory.derive"
                    if getattr(
                        self._result_authority, "is_derive_permit", lambda value: False
                    )(permit)
                    else "original",
                    permit.deadline_epoch_seconds,
                    row["original_deadline"],
                )
            ):
                raise PermissionError("MEMORY_RESULT_BINDING_MISMATCH")
            record = await self.execution_store.get(tenant_id, execution_id)
            if record is None or not any(
                (grant.node_id, grant.execution_agent_id, grant.purpose)
                == (
                    permit.scope.subtask_id,
                    permit.scope.execution_agent_id,
                    permit.scope.purpose,
                )
                for grant in record.context.execution_grants
            ):
                raise PermissionError("MEMORY_RESULT_BINDING_MISMATCH")
            if (
                row.get("checkpoint_mode", "GRAPH") == "NONE"
                and (backend_id != "NO_CHECKPOINT" or namespace != "provider")
            ) or (
                row.get("checkpoint_mode", "GRAPH") == "GRAPH"
                and backend_id not in self.backend_ids
            ):
                raise PermissionError("MEMORY_CHECKPOINT_CAPABILITY_DENIED")
            denial = await self._active(row, ignore_packet_ttl=True)
            if denial:
                raise PermissionError(denial)
            with bind_memory_result_checkpoint_permit(permit):
                yield CheckpointLocation(
                    _scope(row["scope"]), row["runtime_id"], namespace, ()
                )

    @asynccontextmanager
    async def result_checkpoint_scope(
        self, tenant_id, execution_id, backend_id, namespace, permit, result_ref
    ):
        authority = self._result_authority
        if (
            authority is None
            or not callable(getattr(authority, "validate_captured", None))
            or authority.validate_captured(permit, result_ref) is not True
            or self._result_checkpoint_context.get() is not None
        ):
            raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        async with self.result_lease_execution(
            tenant_id, execution_id, backend_id, namespace, permit
        ):
            row = await self._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
                (tenant_id, execution_id),
            )
            token = self._result_checkpoint_context.set((permit, row, result_ref))
            try:
                yield permit
            finally:
                self._result_checkpoint_context.reset(token)

    async def revalidate_result_checkpoint(self, permit, result_ref) -> None:
        current = self._result_checkpoint_context.get()
        if (
            current is None
            or current[0] is not permit
            or current[2] != result_ref
            or self._result_authority is None
            or self._result_authority.validate_captured(permit, result_ref) is not True
        ):
            raise PermissionError("MEMORY_RESULT_BINDING_MISMATCH")
        row = await self._one(
            "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
            (permit.scope.conversation.tenant_id, permit.scope.execution_id),
        )
        if (
            row is None
            or row["runtime_id"] != permit.runtime_id
            or row["execution_revision"] != permit.execution_revision
            or row["packet_revision"] != permit.packet_revision
            or not memory_operation_deadline_matches(
                "memory.derive"
                if getattr(
                    self._result_authority, "is_derive_permit", lambda value: False
                )(permit)
                else "original",
                permit.deadline_epoch_seconds,
                row["original_deadline"],
            )
        ):
            raise PermissionError("MEMORY_RESULT_BINDING_MISMATCH")
        actual = _scope(row["scope"])
        if (actual.conversation, actual.task_id, actual.execution_id) != (
            permit.scope.conversation,
            permit.scope.task_id,
            permit.scope.execution_id,
        ):
            raise PermissionError("MEMORY_RESULT_BINDING_MISMATCH")
        denial = await self._active(row, ignore_packet_ttl=True)
        if denial:
            raise PermissionError(denial)
        if (
            int(self.clock()) >= permit.deadline_epoch_seconds
            or self._result_authority.validate_captured(permit, result_ref) is not True
        ):
            raise PermissionError("MEMORY_RESULT_PUBLICATION_EXPIRED")

    @asynccontextmanager
    async def guard(
        self,
        thread_id: str,
        backend_id: str,
        namespace: str,
        *,
        pending_writes: bool = False,
    ) -> AsyncIterator[CheckpointLocation]:
        result_scope = self._result_checkpoint_context.get()
        if result_scope is not None:
            permit, row, result_ref = result_scope
            if (
                self._result_authority is None
                or self._result_authority.validate_captured(permit, result_ref)
                is not True
                or thread_id != row["root_thread_id"]
                or namespace != {"official": "", "owned": "s2:direct:1"}.get(backend_id)
                or backend_id not in self.backend_ids
            ):
                raise PermissionError("MEMORY_CHECKPOINT_CAPABILITY_DENIED")
            await self.connection.execute(
                self._sql(
                    "INSERT INTO {namespace} (thread_id,backend_id,checkpoint_ns,pending_writes) VALUES (%s,%s,%s,%s) ON CONFLICT (thread_id,backend_id,checkpoint_ns) DO UPDATE SET pending_writes={namespace}.pending_writes OR EXCLUDED.pending_writes"
                ),
                (thread_id, backend_id, namespace, pending_writes),
            )
            yield CheckpointLocation(permit.scope, thread_id, namespace, ())
            return
        capability = self.current_wait_checkpoint_capability()
        if capability is not None:
            _, row = self._wait_checkpoint_context.get()
            if (
                thread_id != row["root_thread_id"]
                or namespace != {"official": "", "owned": "s2:direct:1"}.get(backend_id)
                or backend_id not in self.backend_ids
            ):
                raise PermissionError("MEMORY_CHECKPOINT_CAPABILITY_DENIED")
            await self.connection.execute(
                self._sql(
                    "INSERT INTO {namespace} (thread_id,backend_id,checkpoint_ns,pending_writes) VALUES (%s,%s,%s,%s) ON CONFLICT (thread_id,backend_id,checkpoint_ns) DO UPDATE SET pending_writes={namespace}.pending_writes OR EXCLUDED.pending_writes"
                ),
                (thread_id, backend_id, namespace, pending_writes),
            )
            yield CheckpointLocation(capability.scope, thread_id, namespace, ())
            return
        denial = None
        async with self._transaction():
            row = await self._one(
                "SELECT e.* FROM {execution} e JOIN {member} m USING(tenant_id,execution_id) WHERE m.thread_id=%s FOR UPDATE OF e",
                (thread_id,),
            )
            if row is None:
                raise PermissionError("MEMORY_THREAD_UNREGISTERED")
            if (
                backend_id not in self.backend_ids
                or backend_id not in row["backend_ids"]
            ):
                denial = "MEMORY_BACKEND_UNREGISTERED"
            else:
                try:
                    denial = await self._active(row)
                except Exception:  # noqa: BLE001 - 技术权威不可用也须先持久阻断
                    denial = "MEMORY_AUTHORITY_UNAVAILABLE"
            if denial:
                if row["state"] == "ACTIVE":
                    await self.connection.execute(
                        self._sql(
                            "UPDATE {execution} SET state='BLOCKED',fence_revision=fence_revision+1 WHERE tenant_id=%s AND execution_id=%s"
                        ),
                        (row["tenant_id"], row["execution_id"]),
                    )
            else:
                await self.connection.execute(
                    self._sql(
                        "INSERT INTO {namespace} (thread_id,backend_id,checkpoint_ns,pending_writes) VALUES (%s,%s,%s,%s) "
                        "ON CONFLICT (thread_id,backend_id,checkpoint_ns) DO UPDATE SET pending_writes={namespace}.pending_writes OR EXCLUDED.pending_writes"
                    ),
                    (thread_id, backend_id, namespace, pending_writes),
                )
                yield CheckpointLocation(_scope(row["scope"]), thread_id, namespace, ())
        if denial:
            raise PermissionError(denial)

    @asynccontextmanager
    async def guard_for_refresh_checkpoint(
        self,
        thread_id: str,
        backend_id: str,
        namespace: str,
        *,
        pending_writes: bool = False,
    ):
        if self.current_wait_checkpoint_capability() is not None:
            async with self.guard(
                thread_id, backend_id, namespace, pending_writes=pending_writes
            ) as owner:
                yield owner
            return
        denial = None
        async with self._transaction():
            row = await self._one(
                "SELECT e.* FROM {execution} e JOIN {member} m USING(tenant_id,execution_id) WHERE m.thread_id=%s FOR UPDATE OF e",
                (thread_id,),
            )
            if row is None:
                raise PermissionError("MEMORY_THREAD_UNREGISTERED")
            if (
                backend_id not in self.backend_ids
                or backend_id not in row["backend_ids"]
            ):
                denial = "MEMORY_BACKEND_UNREGISTERED"
            else:
                try:
                    denial = await self._active(row, defer_packet_ttl=True)
                except Exception:  # noqa: BLE001 - 权威异常仍拒绝写入
                    denial = "MEMORY_AUTHORITY_UNAVAILABLE"
            if denial:
                if row["state"] == "ACTIVE" and denial != "MEMORY_PACKET_EXPIRED":
                    await self.connection.execute(
                        self._sql(
                            "UPDATE {execution} SET state='BLOCKED',fence_revision=fence_revision+1 WHERE tenant_id=%s AND execution_id=%s"
                        ),
                        (row["tenant_id"], row["execution_id"]),
                    )
            else:
                await self.connection.execute(
                    self._sql(
                        "INSERT INTO {namespace} (thread_id,backend_id,checkpoint_ns,pending_writes) VALUES (%s,%s,%s,%s) ON CONFLICT (thread_id,backend_id,checkpoint_ns) DO UPDATE SET pending_writes={namespace}.pending_writes OR EXCLUDED.pending_writes"
                    ),
                    (thread_id, backend_id, namespace, pending_writes),
                )
                yield CheckpointLocation(_scope(row["scope"]), thread_id, namespace, ())
        if denial:
            raise PermissionError(denial)

    async def register_child(self, parent_thread_id: str, thread_id: str) -> None:
        async with self.guard(parent_thread_id, next(iter(self.backend_ids)), ""):
            row = await self._one(
                "SELECT * FROM {member} WHERE thread_id=%s", (parent_thread_id,)
            )
            owner = await self._one(
                "SELECT root_thread_id FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
                (row["tenant_id"], row["execution_id"]),
            )
            if (
                not thread_id.startswith(owner["root_thread_id"] + ":child:")
                or thread_id == parent_thread_id
            ):
                raise PermissionError("MEMORY_CHILD_ID_INVALID")
            await self.connection.execute(
                self._sql(
                    "INSERT INTO {member} (thread_id,tenant_id,execution_id,parent_thread_id,dependencies) VALUES (%s,%s,%s,%s,%s)"
                ),
                (
                    thread_id,
                    row["tenant_id"],
                    row["execution_id"],
                    parent_thread_id,
                    Jsonb(row["dependencies"]),
                ),
            )

    async def check_runtime(self, runtime_id: str, tenant_id: str) -> None:
        async with self._transaction():
            row = await self._one(
                "SELECT execution_id,checkpoint_mode FROM {execution} WHERE runtime_id=%s AND tenant_id=%s",
                (runtime_id, tenant_id),
            )
        if row is None:
            raise PermissionError("MEMORY_EXECUTION_OWNER_REQUIRED")
        async with self.guard_execution(
            tenant_id,
            row["execution_id"],
            "NO_CHECKPOINT"
            if row["checkpoint_mode"] == "NONE"
            else next(iter(self.backend_ids)),
            "provider" if row["checkpoint_mode"] == "NONE" else "",
        ):
            pass

    @asynccontextmanager
    async def guard_execution(
        self, tenant_id: str, execution_id: str, backend_id: str, namespace: str
    ):
        denial = None
        async with self._transaction():
            row = await self._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                (tenant_id, execution_id),
            )
            if row is not None and row.get("checkpoint_mode", "GRAPH") == "NONE":
                if backend_id != "NO_CHECKPOINT" or namespace != "provider":
                    denial = "MEMORY_CHECKPOINT_CAPABILITY_DENIED"
                else:
                    try:
                        denial = await self._active(row)
                    except Exception:  # noqa: BLE001 - 本机权威不可用先持久阻断
                        denial = "MEMORY_AUTHORITY_UNAVAILABLE"
                if denial:
                    if row["state"] == "ACTIVE":
                        await self.connection.execute(
                            self._sql(
                                "UPDATE {execution} SET state='BLOCKED',fence_revision=fence_revision+1 WHERE tenant_id=%s AND execution_id=%s"
                            ),
                            (tenant_id, execution_id),
                        )
                else:
                    yield CheckpointLocation(
                        _scope(row["scope"]), row["runtime_id"], namespace, ()
                    )
        if row is None:
            raise PermissionError("MEMORY_EXECUTION_OWNER_REQUIRED")
        if row.get("checkpoint_mode", "GRAPH") == "NONE":
            if denial:
                raise PermissionError(denial)
            return
        async with self.guard(row["runtime_id"], backend_id, namespace) as owner:
            yield owner

    async def scope_for(
        self, tenant_id: str, execution_id: str
    ) -> ExecutionScope | None:
        async with self._transaction():
            row = await self._one(
                "SELECT scope FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
                (tenant_id, execution_id),
            )
            return None if row is None else _scope(row["scope"])

    async def block_for_erasure(
        self, scope: ExecutionScope, source: SourceDependency
    ) -> ThreadErasurePlan | None:
        async with self._transaction():
            row = await self._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                (scope.conversation.tenant_id, scope.execution_id),
            )
            if (
                row is None
                or row.get("checkpoint_mode", "GRAPH") != "GRAPH"
                or _scope(row["scope"]) != scope
                or source not in _dependencies(row["dependencies"])
            ):
                return None
            if row["state"] == "REFRESH_PENDING":
                aborted = await self._one(
                    "UPDATE {resume} SET candidate_phase='ABORTED',result_code='SOURCE_REVOKED',receipt_state='REVOKED',dispatch_allowed=false,authorization_binding=NULL,next_wait_event_id=NULL WHERE tenant_id=%s AND execution_id=%s AND record_kind='RESUME' AND candidate_id=%s AND candidate_phase='PENDING' RETURNING receipt_ref",
                    (
                        row["tenant_id"],
                        row["execution_id"],
                        row["pending_resume_request_id"],
                    ),
                )
                if aborted is None:
                    raise ValueError("MEMORY_REFRESH_FINAL_RECEIPT_REQUIRED")
            if row["state"] not in {"REVOKED", "SCRUBBED", "DELETED"}:
                await self.connection.execute(
                    self._sql(
                        "UPDATE {execution} SET state='REVOKED',fence_revision=fence_revision+1"
                        + (
                            ",pending_resume_request_id=NULL,pending_candidate_digest=NULL,pending_packet_revision=NULL,pending_context_fingerprint=NULL"
                            if "pending_resume_request_id" in row
                            else ""
                        )
                        + " WHERE tenant_id=%s AND execution_id=%s"
                    ),
                    (row["tenant_id"], row["execution_id"]),
                )
                row["fence_revision"] += 1
        # 先提交持久门禁；后端盘点失败不能回滚REVOKED。
        async with self._transaction():
            row = await self._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                (scope.conversation.tenant_id, scope.execution_id),
            )
            members = await self._members(row)
            try:
                authorizations = await (
                    await self.connection.execute(
                        self._sql(
                            "SELECT resume_request_id,result_code FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND result_code IN ('DELETE_PENDING','DELETED') ORDER BY resume_request_id"
                        ),
                        (row["tenant_id"], row["execution_id"]),
                    )
                ).fetchall()
                authorized = False
                for authorization in authorizations:
                    event = _erasure_event(authorization["resume_request_id"])
                    if (
                        event is not None
                        and authorization["result_code"]
                        in {"DELETE_PENDING", "DELETED"}
                        and await self.source_authority.revoked(scope, source, event)
                    ):
                        authorized = True
                        break
                complete = (
                    authorized
                    and row["registry_complete"]
                    and await self._inventory_complete(row, members)
                )
            except Exception:  # noqa: BLE001 - 只转换盘点失败，保留门禁且不输出驱动错误
                complete = False
            return ThreadErasurePlan(
                scope,
                row["operation_hash"],
                row["execution_revision"],
                row["root_thread_id"],
                tuple(
                    ThreadBinding(
                        member["thread_id"],
                        member["parent_thread_id"],
                        _dependencies(member["dependencies"]),
                    )
                    for member in members
                ),
                "REVOKED",
                complete,
                True,
                True,
                frozenset(row["backend_ids"]),
                fence_revision=row["fence_revision"],
            )

    async def mark_deleted(
        self, plan: ThreadErasurePlan, verification: Verification
    ) -> bool:
        expected = {
            (backend, member.thread_id)
            for backend in plan.backend_ids
            for member in plan.threads
        }
        if (
            len(verification) != len(expected)
            or {(backend, thread) for backend, thread, _ in verification} != expected
            or any(not residue.empty for _, _, residue in verification)
        ):
            return False
        async with self._transaction():
            row = await self._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                (plan.scope.conversation.tenant_id, plan.scope.execution_id),
            )
            if (
                row is None
                or row["state"] not in {"REVOKED", "DELETED"}
                or row["execution_revision"] != plan.execution_revision
                or row["fence_revision"] != plan.fence_revision
                or row["operation_hash"] != plan.operation_id
                or _scope(row["scope"]) != plan.scope
                or frozenset(row["backend_ids"]) != plan.backend_ids
            ):
                return False
            members = await self._members(row)
            actual = tuple(
                ThreadBinding(
                    member["thread_id"],
                    member["parent_thread_id"],
                    _dependencies(member["dependencies"]),
                )
                for member in members
            )
            if actual != plan.threads or not await self._inventory_complete(
                row, members
            ):
                return False
            await self.connection.execute(
                self._sql(
                    "UPDATE {execution} SET state='DELETED' WHERE tenant_id=%s AND execution_id=%s"
                ),
                (row["tenant_id"], row["execution_id"]),
            )
            return True

    async def set_wait(
        self, runtime_id: str, tenant_id: str, wait_event_id: str
    ) -> None:
        async with self.guard(runtime_id, next(iter(self.backend_ids)), ""):
            row = await self._one(
                "SELECT wait_event_id FROM {execution} WHERE runtime_id=%s AND tenant_id=%s",
                (runtime_id, tenant_id),
            )
            if row is None or row["wait_event_id"] not in {None, wait_event_id}:
                raise ValueError("MEMORY_WAIT_CONFLICT_409")
            await self.connection.execute(
                self._sql(
                    "UPDATE {execution} SET wait_event_id=%s WHERE runtime_id=%s AND tenant_id=%s"
                ),
                (wait_event_id, runtime_id, tenant_id),
            )

    async def resume(
        self, runtime_id: str, tenant_id: str, request: ResumeRequest
    ) -> ResumeReceipt:
        fingerprint = _hash(asdict(request))
        async with self._transaction():
            row = await self._one(
                "SELECT * FROM {execution} WHERE runtime_id=%s AND tenant_id=%s FOR UPDATE",
                (runtime_id, tenant_id),
            )
            if row is None:
                raise PermissionError("MEMORY_EXECUTION_OWNER_REQUIRED")
            key = (
                tenant_id,
                row["execution_id"],
                _receipt_key("RESUME", request.resume_request_id),
            )
            legacy = await self._one(
                "SELECT * FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s",
                (tenant_id, row["execution_id"], request.resume_request_id),
            )
            if legacy is not None:
                raise ValueError("MEMORY_RECEIPT_PROTOCOL_UPGRADE_REQUIRED")
            previous = await self._one(
                "SELECT * FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s",
                key,
            )
            if previous:
                if previous["request_hash"] != fingerprint:
                    raise ValueError("MEMORY_RESUME_CONFLICT_409")
                return ResumeReceipt(previous["result_code"], previous["receipt_ref"])
            if (
                request.wait_event_id != row["wait_event_id"]
                or request.packet_revision != row["packet_revision"]
                or request.expected_execution_revision != row["execution_revision"]
                or request.operation_hash != row["operation_hash"]
            ):
                raise ValueError("MEMORY_RESUME_CONFLICT_409")
            if row["state"] in {"REVOKED", "DELETED", "BLOCKED"}:
                code = "MEMORY_THREAD_FENCED"
            elif int(self.clock()) >= row["original_deadline"]:
                code = "EXPIRED"
                await self.connection.execute(
                    self._sql(
                        "UPDATE {execution} SET state='EXPIRED',fence_revision=fence_revision+1 WHERE tenant_id=%s AND execution_id=%s AND state='ACTIVE'"
                    ),
                    key[:2],
                )
            elif request.mode == "paid":
                code = "CONTINUATION_AUTH_UNSUPPORTED"
            elif request.mode == "refresh":
                if row["refresh_count"] >= 3:
                    code = "MEMORY_REFRESH_LIMIT"
                else:
                    code = "MEMORY_REFRESH_AUTH_UNSUPPORTED"
                    await self.connection.execute(
                        self._sql(
                            "UPDATE {execution} SET refresh_count=refresh_count+1 WHERE tenant_id=%s AND execution_id=%s"
                        ),
                        key[:2],
                    )
            elif await self._active(row):
                code = "MEMORY_AUTHORITY_REFRESH_REQUIRED"
            else:
                code = "CPU_CONFIRMED"
            receipt = ResumeReceipt(code, "memory-resume:" + uuid4().hex)
            await self.connection.execute(
                self._sql(
                    "INSERT INTO {resume} (tenant_id,execution_id,resume_request_id,request_hash,result_code,receipt_ref) VALUES (%s,%s,%s,%s,%s,%s)"
                ),
                (*key, fingerprint, receipt.code, receipt.receipt_ref),
            )
            return receipt

    async def prepare_cleanup(
        self,
        tenant_id,
        execution_id,
        event_id,
        expected_execution_revision,
        source_dependencies,
    ):
        if (
            not event_id
            or not source_dependencies
            or len(set(source_dependencies)) != len(source_dependencies)
        ):
            return None
        fingerprint = _hash(
            {
                "event_id": event_id,
                "revision": expected_execution_revision,
                "dependencies": sorted(
                    (asdict(dep) for dep in source_dependencies),
                    key=lambda dep: json.dumps(dep, sort_keys=True),
                ),
            }
        )
        key = (tenant_id, execution_id, _receipt_key("ERASURE", event_id))
        async with self._transaction():
            row = await self._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                key[:2],
            )
            if row is None:
                return None
            legacy = await self._one(
                "SELECT * FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s",
                (tenant_id, execution_id, "erase:" + event_id),
            )
            previous = await self._one(
                "SELECT * FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s",
                key,
            )
            if previous and previous["request_hash"] != fingerprint:
                raise ValueError("MEMORY_ERASURE_EVENT_CONFLICT_409")
            scope = _scope(row["scope"])
            if row["execution_revision"] != expected_execution_revision or not set(
                source_dependencies
            ).issubset(_dependencies(row["dependencies"])):
                raise ValueError("MEMORY_ERASURE_REVISION_CONFLICT_409")
            if (
                previous
                and previous["result_code"] == "DELETED"
                and row["state"] == "DELETED"
            ):
                return (
                    scope,
                    source_dependencies[0],
                    ThreadCleanupReceipt("DELETED", previous["receipt_ref"]),
                )
            if not all(
                [
                    await self.source_authority.revoked(scope, source, event_id)
                    for source in source_dependencies
                ]
            ):
                return None
            if row["state"] == "REFRESH_PENDING":
                aborted = await self._one(
                    "UPDATE {resume} SET candidate_phase='ABORTED',result_code='SOURCE_REVOKED',receipt_state='REVOKED',dispatch_allowed=false,authorization_binding=NULL,next_wait_event_id=NULL WHERE tenant_id=%s AND execution_id=%s AND record_kind='RESUME' AND candidate_id=%s AND candidate_phase='PENDING' RETURNING receipt_ref",
                    (*key[:2], row["pending_resume_request_id"]),
                )
                if aborted is None:
                    raise ValueError("MEMORY_REFRESH_FINAL_RECEIPT_REQUIRED")
            if row["state"] not in {"REVOKED", "SCRUBBED", "DELETED"}:
                await self.connection.execute(
                    self._sql(
                        "UPDATE {execution} SET state='REVOKED',fence_revision=fence_revision+1"
                        + (
                            ",pending_resume_request_id=NULL,pending_candidate_digest=NULL,pending_packet_revision=NULL,pending_context_fingerprint=NULL"
                            if "pending_resume_request_id" in row
                            else ""
                        )
                        + " WHERE tenant_id=%s AND execution_id=%s"
                    ),
                    key[:2],
                )
            if not previous and legacy is None:
                await self.connection.execute(
                    self._sql(
                        "INSERT INTO {resume} (tenant_id,execution_id,resume_request_id,request_hash,result_code,receipt_ref) VALUES (%s,%s,%s,%s,'DELETE_PENDING',%s)"
                    ),
                    (*key, fingerprint, "memory-threads:" + uuid4().hex),
                )
            prepared = scope, source_dependencies[0], None
        if legacy is not None:
            raise ValueError("MEMORY_RECEIPT_PROTOCOL_UPGRADE_REQUIRED")
        return prepared

    async def erase_if_no_checkpoint(
        self, scope: ExecutionScope, event_id: str, expected_execution_revision: int
    ) -> ThreadCleanupReceipt | None:
        key = (
            scope.conversation.tenant_id,
            scope.execution_id,
            _receipt_key("ERASURE", event_id),
        )
        async with self._transaction():
            row = await self._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                key[:2],
            )
            if row is None or row.get("checkpoint_mode", "GRAPH") != "NONE":
                return None
            receipt = await self._one(
                "SELECT * FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s",
                key,
            )
            if (
                receipt is None
                or row["state"] not in {"REVOKED", "DELETED"}
                or row["root_thread_id"] is not None
                or row["backend_ids"]
                or not row["registry_complete"]
                or _scope(row["scope"]) != scope
                or row["execution_revision"] != expected_execution_revision
                or await self._members(row)
            ):
                return ThreadCleanupReceipt("DELETE_PENDING")
            for inventory in self.inventories:
                if await inventory.entries(row["runtime_id"]):
                    return ThreadCleanupReceipt("DELETE_PENDING")
            await self.connection.execute(
                self._sql(
                    "UPDATE {execution} SET state='DELETED' WHERE tenant_id=%s AND execution_id=%s"
                ),
                key[:2],
            )
            await self.connection.execute(
                self._sql(
                    "UPDATE {resume} SET result_code='DELETED' WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s"
                ),
                key,
            )
            return ThreadCleanupReceipt("DELETED", receipt["receipt_ref"])

    async def finish_cleanup(
        self, tenant_id, execution_id, event_id
    ) -> ThreadCleanupReceipt:
        key = (tenant_id, execution_id, _receipt_key("ERASURE", event_id))
        async with self._transaction():
            row = await self._one(
                "SELECT state FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                key[:2],
            )
            if row is None or row["state"] != "DELETED":
                return ThreadCleanupReceipt("DELETE_PENDING")
            receipt = await self._one(
                "UPDATE {resume} SET result_code='DELETED' WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s RETURNING receipt_ref",
                key,
            )
            if receipt is None:
                return ThreadCleanupReceipt("DELETE_PENDING")
            return ThreadCleanupReceipt("DELETED", receipt["receipt_ref"])
