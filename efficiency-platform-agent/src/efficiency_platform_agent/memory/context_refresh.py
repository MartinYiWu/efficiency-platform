"""原执行授权刷新协调器；不授予实际发送能力。"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict, replace
from uuid import uuid4
from weakref import ref

from sqlalchemy import text

from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionContext,
    MemoryGraphResumeCapability,
    MemoryWaitCheckpointCapability,
)
from efficiency_platform_agent.core.memory_refresh import (
    CandidatePhase,
    CheckpointMode,
    MemoryContextResumeReceipt,
    MemoryContextWait,
    RefreshState,
    ResumeCode,
    ResumeMode,
)
from efficiency_platform_agent.persistence.memory_execution import _fingerprint
from efficiency_platform_agent.persistence.memory_execution_registry import (
    _receipt_key,
    _scope,
)
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)


def validate_refresh_context(old, new, original_deadline, now):
    normalized = replace(
        new.packet,
        packet_revision=old.packet.packet_revision,
        execution_revision=old.packet.execution_revision,
        issued_at=old.packet.issued_at,
        expires_at=old.packet.expires_at,
    )
    if (
        normalized != old.packet
        or replace(new, packet=old.packet, packet_digest=old.packet_digest) != old
        or memory_packet_digest(old.packet) != old.packet_digest
        or memory_packet_digest(new.packet) != new.packet_digest
        or memory_packet_semantic_digest(old.packet) != old.semantic_snapshot_digest
        or memory_packet_semantic_digest(new.packet) != old.semantic_snapshot_digest
    ):
        raise ValueError("SOURCE_CHANGED")
    if (
        new.packet.packet_revision <= old.packet.packet_revision
        or new.packet.execution_revision != old.packet.execution_revision
        or new.packet.expires_at > original_deadline
        or new.packet.expires_at - new.packet.issued_at
        > min(60, old.packet.expires_at - old.packet.issued_at)
        or new.packet.issued_at > now
    ):
        raise ValueError("MEMORY_REVISION_CONFLICT")


class MemoryContextRefreshService:
    def __init__(
        self,
        registry,
        journal,
        *,
        fault_hook=None,
        frame_verifier=None,
        checkpoint_verifier=None,
        binding_updater=None,
        wait_task_resolver=None,
    ):
        self.registry, self.journal = registry, journal
        self.fault_hook = fault_hook
        self.frame_verifier: (
            Callable[[MemoryContextWait, str], Awaitable[bool]] | None
        ) = frame_verifier
        self.checkpoint_verifier = checkpoint_verifier
        self.binding_updater = binding_updater
        self.wait_task_resolver = wait_task_resolver
        self._wait_capabilities = {}
        self._resume_capabilities = {}

    async def begin_wait_intent(
        self,
        scope,
        runtime_id,
        operation_id,
        attempt,
        phase,
        *,
        canonical_request_hmac=None,
        stage_id=None,
        stage_slot=None,
    ):
        registry = self.registry
        key = (scope.conversation.tenant_id, scope.execution_id)
        async with registry._transaction():
            row = await registry._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                key,
            )
            if row is None or row["runtime_id"] != runtime_id:
                raise PermissionError("CONTEXT_SCOPE_MISMATCH")
            registered_scope = _scope(row["scope"])
            alternate_scope = registered_scope != scope
            if alternate_scope and (
                row["checkpoint_mode"] != "NONE"
                or phase.value not in {"PREPARED", "RESERVED"}
                or (
                    registered_scope.conversation,
                    registered_scope.task_id,
                    registered_scope.execution_id,
                )
                != (scope.conversation, scope.task_id, scope.execution_id)
            ):
                raise PermissionError("CONTEXT_SCOPE_MISMATCH")
            if row["checkpoint_mode"] != "NONE" and self.checkpoint_verifier is None:
                raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
            if row["state"] not in {"ACTIVE", "WAITING_CONTEXT"}:
                raise PermissionError("ACCESS_REVOKED")
            async with self.journal.execution_store.engine.begin() as conn:
                owner, record = await self.journal.lock_owner(
                    conn, scope.conversation, scope.execution_id
                )
                await self._check_owner(row, record)
                if alternate_scope and (
                    record.runtime_kind != "CUSTOMER_SERVICE"
                    or not any(
                        (grant.node_id, grant.execution_agent_id, grant.purpose)
                        == (scope.subtask_id, scope.execution_agent_id, scope.purpose)
                        for grant in record.context.execution_grants
                    )
                ):
                    raise PermissionError("CONTEXT_SCOPE_MISMATCH")
                if int(registry.clock()) < record.context.packet.expires_at:
                    raise ValueError("MEMORY_WAIT_NOT_EXPIRED")
                wait_id = (
                    row["wait_event_id"]
                    if row["state"] == "WAITING_CONTEXT"
                    else "memory-wait-" + uuid4().hex
                )
                wait = MemoryContextWait(
                    "memory-context-wait/1",
                    wait_id,
                    runtime_id,
                    scope.task_id,
                    scope.execution_id,
                    scope.conversation,
                    record.context.packet.packet_revision,
                    record.execution_revision,
                    owner["current_context_fingerprint"],
                    record.request_fingerprint,
                    operation_id,
                    record.context.packet.semantic_input_hash,
                    canonical_request_hmac,
                    attempt,
                    stage_id,
                    stage_slot,
                    CheckpointMode.NONE,
                    None,
                    None,
                    phase,
                    record.deadline_epoch_seconds,
                    row["refresh_count"],
                )
                operation_binding = None
                if phase.value != "BEFORE_PREPARE":
                    operation_binding = await self.journal.verify_operation(
                        conn, wait, record, operation_scope=scope
                    )
                    if not await self._frame_available(wait):
                        raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
                existing = await self.journal.record(
                    conn, scope.conversation, scope.execution_id, "WAIT", wait_id
                )
                if existing is None:
                    wait_body = {"context": record.context.metadata()}
                    if operation_binding is not None:
                        wait_body.update(operation_binding)
                    if record.runtime_kind == "OPERATIONS":
                        wait_body["run_anchor"] = await self.journal.run_anchor(
                            conn, record
                        )
                    await self.journal.insert(
                        conn,
                        wait,
                        record,
                        "WAIT",
                        wait_id,
                        wait_body,
                        {
                            "wait_event_id": wait_id.encode(),
                            "wait_phase": phase.value,
                            "checkpoint_mode": row["checkpoint_mode"],
                            "phase": "BUILDING",
                        },
                    )
                elif (
                    self.journal.wait(existing, row["refresh_count"], draft=True)
                    != wait
                ):
                    raise ValueError("MEMORY_RESUME_CONFLICT")
                elif phase.value != "BEFORE_PREPARE":
                    persisted_binding = await self.journal.verify_wait_operation(
                        conn, existing, record
                    )
                    if persisted_binding != operation_binding:
                        raise ValueError("MEMORY_RESUME_CONFLICT")
            if row["state"] == "ACTIVE":
                await registry.connection.execute(
                    registry._sql(
                        "UPDATE {execution} SET state='WAITING_CONTEXT',wait_event_id=%s,wait_status='BUILDING',wait_packet_revision=packet_revision,wait_context_fingerprint=%s,current_context_fingerprint=%s,wait_phase=%s,fence_revision=fence_revision+1 WHERE tenant_id=%s AND execution_id=%s"
                    ),
                    (
                        wait_id,
                        wait.expected_current_context_fingerprint,
                        wait.expected_current_context_fingerprint,
                        phase.value,
                        *key,
                    ),
                )
        return wait_id

    async def _check_owner(self, row, record):
        registry = self.registry
        scope = _scope(row["scope"])
        packet = record.context.packet
        if (
            record.state != "ACTIVE"
            or record.runtime_id != row["runtime_id"]
            or record.request_fingerprint != row["operation_hash"]
            or record.execution_revision != row["execution_revision"]
            or record.deadline_epoch_seconds != row["original_deadline"]
            or (packet.scope, packet.task_id, packet.execution_id)
            != (scope.conversation, scope.task_id, scope.execution_id)
            or record.context.semantic_snapshot_digest != row["semantic_digest"]
            or memory_packet_digest(packet) != record.context.packet_digest
            or memory_packet_semantic_digest(packet)
            != record.context.semantic_snapshot_digest
            or [asdict(dep) for dep in packet.safety_dependencies]
            != row["dependencies"]
            or (record.grant_epoch, record.source_epoch, record.deletion_epoch)
            != (packet.grant_epoch, packet.source_epoch, packet.deletion_epoch)
            or not row["registry_complete"]
        ):
            raise PermissionError("ACCESS_REVOKED")
        if int(registry.clock()) >= record.deadline_epoch_seconds:
            raise PermissionError("EXECUTION_EXPIRED")
        if not await registry.source_authority.current(
            scope, packet.safety_dependencies
        ):
            raise PermissionError("SOURCE_REVOKED")
        if row["checkpoint_mode"] == "NONE":
            if (
                row["root_thread_id"] is not None
                or row["backend_ids"]
                or await registry._members(row)
            ):
                raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
            for inventory in registry.inventories:
                if await inventory.entries(row["runtime_id"]):
                    raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        elif self.checkpoint_verifier is None or not await registry._inventory_complete(
            row, await registry._members(row)
        ):
            raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")

    async def finish_wait(
        self, scope, execution_id, wait_id, *, checkpoint_ns=None, checkpoint_id=None
    ):
        registry = self.registry
        key = (scope.tenant_id, execution_id)
        async with registry._transaction():
            row = await registry._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                key,
            )
            if (
                row is None
                or _scope(row["scope"]).conversation != scope
                or row["wait_event_id"] != wait_id
                or row["state"] != "WAITING_CONTEXT"
            ):
                raise ValueError("MEMORY_WAIT_CONSUMED")
            async with self.journal.execution_store.engine.begin() as conn:
                _, record = await self.journal.lock_owner(conn, scope, execution_id)
                await self._check_owner(row, record)
                journal = await self.journal.record(
                    conn, scope, execution_id, "WAIT", wait_id
                )
                if journal is None or journal["phase"] not in {"BUILDING", "READY"}:
                    raise ValueError("MEMORY_AUTHORITY_UNAVAILABLE")
                await self.journal.verify_wait_operation(conn, journal, record)
                if journal["checkpoint_mode"] == "GRAPH":
                    checkpoint = (
                        (checkpoint_ns, checkpoint_id)
                        if journal["phase"] == "BUILDING"
                        else None
                    )
                    if checkpoint is not None and (
                        checkpoint_ns is None or not checkpoint_id
                    ):
                        raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
                    wait = self.journal.wait(
                        journal, row["refresh_count"], checkpoint=checkpoint
                    )
                    if (
                        self.checkpoint_verifier is None
                        or checkpoint_ns is None
                        or not checkpoint_id
                        or not await self.checkpoint_verifier(
                            wait, checkpoint_ns, checkpoint_id
                        )
                    ):
                        raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
                else:
                    wait = self.journal.wait(journal, row["refresh_count"])
                    if checkpoint_ns is not None or checkpoint_id is not None:
                        raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
                await conn.execute(
                    text(
                        "UPDATE agent_memory_context_refresh SET phase='READY',checkpoint_ns=:ns,checkpoint_id=:checkpoint WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='WAIT' AND record_id=:wait AND phase='BUILDING'"
                    ),
                    self.journal.key(scope, execution_id)
                    | {
                        "wait": wait_id.encode(),
                        "ns": None if checkpoint_ns is None else checkpoint_ns.encode(),
                        "checkpoint": None
                        if checkpoint_id is None
                        else checkpoint_id.encode(),
                    },
                )
            await registry.connection.execute(
                registry._sql(
                    "UPDATE {execution} SET wait_status='READY',wait_checkpoint_ns=%s,wait_checkpoint_id=%s WHERE tenant_id=%s AND execution_id=%s"
                ),
                (checkpoint_ns, checkpoint_id, *key),
            )

    async def get_wait(self, scope, execution_id, wait_event_id=None):
        registry = self.registry
        async with registry._transaction():
            row = await registry._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                (scope.tenant_id, execution_id),
            )
            if row is None:
                return None
            if _scope(row["scope"]).conversation != scope:
                raise PermissionError("CONTEXT_SCOPE_MISMATCH")
            if wait_event_id is None:
                if row["state"] != "WAITING_CONTEXT" or row["wait_status"] != "READY":
                    return None
            elif row["state"] not in {"ACTIVE", "WAITING_CONTEXT", "REFRESH_PENDING"}:
                raise PermissionError("ACCESS_REVOKED")
            async with self.journal.execution_store.engine.begin() as conn:
                _, record = await self.journal.lock_owner(conn, scope, execution_id)
                await self._check_owner(row, record)
                journal = await self.journal.record(
                    conn,
                    scope,
                    execution_id,
                    "WAIT",
                    row["wait_event_id"] if wait_event_id is None else wait_event_id,
                )
                allowed = (
                    {"READY"}
                    if wait_event_id is None
                    else {"READY", "CONSUMED", "SUPERSEDED"}
                )
                if journal is None or journal["phase"] not in allowed:
                    return None
                await self.journal.verify_wait_operation(
                    conn, journal, record, require_not_sent=False
                )
                return self.journal.wait(journal, row["refresh_count"])

    async def validate_manifest_authorization(self, manifest, operation, packet):
        return await self.journal.validate_manifest_authorization(
            manifest,
            operation,
            packet,
            packet_digest=memory_packet_digest(packet),
            semantic_digest=memory_packet_semantic_digest(packet),
        )

    async def validate_execution_manifest(self, manifest, current_record):
        packet = current_record.context.packet
        scope = packet.scope
        registry = self.registry
        async with registry._transaction():
            row = await registry._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                (scope.tenant_id, packet.execution_id),
            )
            if row is None or row["state"] != "ACTIVE":
                return False
            await self._check_owner(row, current_record)
            async with self.journal.execution_store.engine.begin() as conn:
                owner, record = await self.journal.lock_owner(
                    conn, scope, packet.execution_id
                )
                if (
                    record != current_record
                    or row["packet_revision"] != packet.packet_revision
                    or row["current_context_fingerprint"]
                    != owner["current_context_fingerprint"]
                ):
                    return False
                return await self.journal.execution_manifest_locked(
                    conn, manifest, record, owner["current_context_fingerprint"]
                )

    async def get_wait_receipt(self, scope, execution_id, wait_id):
        registry = self.registry
        async with registry._transaction():
            row = await registry._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                (scope.tenant_id, execution_id),
            )
            if row is None or _scope(row["scope"]).conversation != scope:
                raise PermissionError("CONTEXT_SCOPE_MISMATCH")
            if row["state"] != "ACTIVE":
                return None
            prior = await registry._one(
                "SELECT * FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND record_kind='RESUME' AND wait_event_id=%s AND candidate_phase='ACKED' AND current_packet_revision=%s AND current_context_fingerprint=%s",
                (
                    scope.tenant_id,
                    execution_id,
                    wait_id,
                    row["packet_revision"],
                    row["current_context_fingerprint"],
                ),
            )
            if prior is None:
                return None
            async with self.journal.execution_store.engine.begin() as conn:
                owner, record = await self.journal.lock_owner(conn, scope, execution_id)
                await self._check_owner(row, record)
                candidate = await self.journal.record(
                    conn, scope, execution_id, "REFRESH", prior["candidate_id"]
                )
                raw_wait = await self.journal.record(
                    conn, scope, execution_id, "WAIT", wait_id
                )
                if (
                    candidate is None
                    or raw_wait is None
                    or candidate["phase"] != "ACKED"
                    or raw_wait["phase"] != "CONSUMED"
                    or candidate["request_hash"] != prior["request_hash"]
                    or bytes(candidate["receipt_ref"]).decode() != prior["receipt_ref"]
                    or candidate["dispatch_allowed"] != prior["dispatch_allowed"]
                    or candidate["target_context_fingerprint"]
                    != owner["current_context_fingerprint"]
                ):
                    return None
                self.journal.body(candidate)
                self.journal.wait(raw_wait, row["refresh_count"])
                await self.journal.verify_wait_operation(conn, raw_wait, record)
                return self._receipt(prior)

    async def get_wait_outcome(self, scope, execution_id, wait_id):
        receipt = await self.get_wait_receipt(scope, execution_id, wait_id)
        if receipt is not None:
            return receipt
        registry = self.registry
        async with registry._transaction():
            row = await registry._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                (scope.tenant_id, execution_id),
            )
            if row is None or _scope(row["scope"]).conversation != scope:
                raise PermissionError("CONTEXT_SCOPE_MISMATCH")
            if row["state"] not in {"ACTIVE", "WAITING_CONTEXT", "REFRESH_PENDING"}:
                raise PermissionError("ACCESS_REVOKED")
            prior = await registry._one(
                "SELECT * FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND record_kind='RESUME' AND wait_event_id=%s AND candidate_phase='APPLIED_EXPIRED'",
                (scope.tenant_id, execution_id, wait_id),
            )
            if prior is None:
                return None
            async with self.journal.execution_store.engine.begin() as conn:
                _, record = await self.journal.lock_owner(conn, scope, execution_id)
                await self._check_owner(row, record)
                candidate = await self.journal.record(
                    conn, scope, execution_id, "REFRESH", prior["candidate_id"]
                )
                original = await self.journal.record(
                    conn, scope, execution_id, "WAIT", wait_id
                )
                if (
                    candidate is None
                    or original is None
                    or candidate["phase"] != "APPLIED_EXPIRED"
                    or original["phase"] != "SUPERSEDED"
                    or candidate["request_hash"] != prior["request_hash"]
                    or bytes(candidate["receipt_ref"]).decode() != prior["receipt_ref"]
                    or candidate["next_wait_event_id"] is None
                    or bytes(candidate["next_wait_event_id"]).decode()
                    != prior["next_wait_event_id"]
                    or candidate["dispatch_allowed"]
                    or prior["dispatch_allowed"]
                    or candidate["current_context_fingerprint"]
                    != prior["current_context_fingerprint"]
                ):
                    return None
                context = MemoryExecutionContext.from_metadata(
                    self.journal.body(candidate)["context"]
                )
                if (
                    _fingerprint(context.metadata())
                    != prior["current_context_fingerprint"]
                    or context.semantic_snapshot_digest
                    != record.context.semantic_snapshot_digest
                ):
                    return None
                next_wait = await self.journal.record(
                    conn, scope, execution_id, "WAIT", prior["next_wait_event_id"]
                )
                if (
                    next_wait is None
                    or next_wait["phase"] not in {"READY", "CONSUMED", "SUPERSEDED"}
                    or next_wait["expected_current_context_fingerprint"]
                    != prior["current_context_fingerprint"]
                    or next_wait["old_packet_revision"]
                    != prior["current_packet_revision"]
                    or next_wait["operation_id"] != original["operation_id"]
                    or next_wait["attempt"] != original["attempt"]
                    or next_wait["canonical_request_hmac"]
                    != original["canonical_request_hmac"]
                    or next_wait["stage_id"] != original["stage_id"]
                    or next_wait["stage_slot"] != original["stage_slot"]
                    or next_wait["wait_phase"] != original["wait_phase"]
                ):
                    return None
                self.journal.wait(original, row["refresh_count"])
                self.journal.wait(next_wait, row["refresh_count"])
                await self.journal.verify_wait_operation(
                    conn, original, record, require_not_sent=False
                )
                await self.journal.verify_wait_operation(
                    conn, next_wait, record, require_not_sent=False
                )
                return self._receipt(prior)

    @staticmethod
    def _receipt(row):
        return MemoryContextResumeReceipt(
            ResumeCode(row["result_code"]),
            row["receipt_ref"],
            row["wait_event_id"],
            row["packet_revision"],
            row["execution_revision"],
            row["current_packet_revision"],
            row["current_context_fingerprint"],
            row["refresh_count"],
            RefreshState(row["receipt_state"]),
            CandidatePhase(row["candidate_phase"]),
            row["next_wait_event_id"],
            row["dispatch_allowed"],
        )

    async def _fault(self, point):
        if self.fault_hook is not None:
            await self.fault_hook(point)

    async def _frame_available(self, wait):
        return (
            self.frame_verifier is not None
            and int(self.registry.clock()) < wait.original_deadline
            and await self.frame_verifier(wait, wait.runtime_id) is True
        )

    @staticmethod
    def _wait_capability(scope, wait):
        return MemoryWaitCheckpointCapability(
            scope,
            wait.runtime_id,
            wait.wait_event_id,
            wait.logical_operation_id,
            wait.attempt,
            wait.canonical_request_hmac,
            wait.expected_packet_revision,
            wait.expected_execution_revision,
            wait.expected_current_context_fingerprint,
            wait.original_deadline,
            "memory-wait-cap-" + uuid4().hex,
        )

    async def issue_wait_checkpoint_capability(self, scope, execution_id, wait_id):
        conversation = getattr(scope, "conversation", scope)
        registry = self.registry
        async with registry._transaction():
            row = await registry._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                (conversation.tenant_id, execution_id),
            )
            if (
                row is None
                or _scope(row["scope"]).conversation != conversation
                or row["state"] != "WAITING_CONTEXT"
                or row["checkpoint_mode"] != "GRAPH"
                or row["wait_status"] != "BUILDING"
                or row["wait_event_id"] != wait_id
            ):
                raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
            async with self.journal.execution_store.engine.begin() as conn:
                _, record = await self.journal.lock_owner(
                    conn, conversation, execution_id
                )
                await self._check_owner(row, record)
                raw = await self.journal.record(
                    conn, conversation, execution_id, "WAIT", wait_id
                )
                if raw is None or raw["phase"] != "BUILDING":
                    raise PermissionError("MEMORY_WAIT_CONSUMED")
                wait = self.journal.wait(raw, row["refresh_count"], draft=True)
                capability = self._wait_capability(_scope(row["scope"]), wait)
        task = (
            asyncio.current_task()
            if self.wait_task_resolver is None
            else self.wait_task_resolver(wait, wait.runtime_id)
        )
        if not isinstance(task, asyncio.Task) or task.done():
            raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        self._wait_capabilities[capability.capability_ref] = capability, ref(task), wait
        return capability

    def validate_wait_capability(self, capability):
        if not isinstance(capability, MemoryWaitCheckpointCapability):
            return False
        existing = self._wait_capabilities.get(capability.capability_ref)
        task = None if existing is None else existing[1]()
        return (
            existing is not None
            and existing[0] is capability
            and task is not None
            and not task.done()
        )

    def wait_capability_task(self, capability):
        existing = self._wait_capabilities.get(
            getattr(capability, "capability_ref", None)
        )
        return (
            existing[1]()
            if existing is not None and existing[0] is capability
            else None
        )

    def validate_wait_scope_task(self, capability):
        if not self.validate_wait_capability(capability):
            return False
        existing = self._wait_capabilities[capability.capability_ref]
        task = existing[1]()
        if task is asyncio.current_task():
            return True
        return (
            self.wait_task_resolver is not None
            and self.wait_task_resolver(existing[2], capability.runtime_id) is task
        )

    async def claim_resume_start(self, scope, execution_id, wait_id, receipt_ref=None):
        registry = self.registry
        async with registry._transaction():
            row = await registry._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                (scope.tenant_id, execution_id),
            )
            if (
                row is not None
                and _scope(row["scope"]).conversation == scope
                and row["state"] == "REFRESH_PENDING"
            ):
                raise PermissionError("MEMORY_REFRESH_PENDING")
            if (
                row is None
                or _scope(row["scope"]).conversation != scope
                or row["state"] != "ACTIVE"
                or row["checkpoint_mode"] != "GRAPH"
            ):
                raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
            prior = await registry._one(
                "SELECT * FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND record_kind='RESUME' AND wait_event_id=%s AND candidate_phase='ACKED' AND current_packet_revision=%s AND current_context_fingerprint=%s"
                + (" AND receipt_ref=%s" if receipt_ref is not None else ""),
                (
                    scope.tenant_id,
                    execution_id,
                    wait_id,
                    row["packet_revision"],
                    row["current_context_fingerprint"],
                    *((receipt_ref,) if receipt_ref is not None else ()),
                ),
            )
            if (
                prior is None
                or prior["current_packet_revision"] != row["packet_revision"]
                or prior["current_context_fingerprint"]
                != row["current_context_fingerprint"]
            ):
                raise PermissionError("MEMORY_AUTHORITY_UNAVAILABLE")
            receipt_ref = prior["receipt_ref"]
            if prior["dispatch_allowed"] is not True:
                raise PermissionError("CONTINUATION_AUTH_UNSUPPORTED")
            async with self.journal.execution_store.engine.begin() as conn:
                _, record = await self.journal.lock_owner(conn, scope, execution_id)
                await self._check_owner(row, record)
                raw = await self.journal.record(
                    conn, scope, execution_id, "WAIT", wait_id
                )
                if (
                    raw is None
                    or raw["phase"] != "CONSUMED"
                    or raw["resume_start"] != "READY"
                ):
                    raise PermissionError("MEMORY_WAIT_CONSUMED")
                wait = self.journal.wait(raw, row["refresh_count"])
                if wait.wait_phase.value != "BEFORE_PREPARE":
                    raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
                if (
                    not await self._frame_available(wait)
                    or self.checkpoint_verifier is None
                    or not await self.checkpoint_verifier(
                        wait, wait.checkpoint_ns, wait.checkpoint_id
                    )
                ):
                    raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
                changed = await conn.execute(
                    text(
                        "UPDATE agent_memory_context_refresh SET resume_start='CLAIMED' WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='WAIT' AND record_id=:wait AND resume_start='READY'"
                    ),
                    self.journal.key(scope, execution_id) | {"wait": wait_id.encode()},
                )
                if changed.rowcount != 1:
                    raise PermissionError("MEMORY_WAIT_CONSUMED")
                capability = MemoryGraphResumeCapability(
                    self._wait_capability(_scope(row["scope"]), wait),
                    receipt_ref,
                    wait.checkpoint_ns,
                    wait.checkpoint_id,
                    row["packet_revision"],
                    row["current_context_fingerprint"],
                    "memory-resume-cap-" + uuid4().hex,
                )
        self._resume_capabilities[capability.capability_ref] = (
            capability,
            ref(asyncio.current_task()),
            False,
        )
        return capability

    async def consume_resume(self, capability, config):
        if not isinstance(capability, MemoryGraphResumeCapability):
            return False
        existing = self._resume_capabilities.get(capability.capability_ref)
        if (
            existing is None
            or existing[0] is not capability
            or existing[2]
            or existing[1]() is not asyncio.current_task()
        ):
            return False
        self._resume_capabilities[capability.capability_ref] = (
            capability,
            existing[1],
            True,
        )
        configurable = config.get("configurable", {})
        if (
            configurable.get("thread_id") != capability.binding.runtime_id
            or configurable.get("checkpoint_ns", "")
            not in {capability.checkpoint_ns, "s2:direct:1"}
            or configurable.get("checkpoint_id", capability.checkpoint_id)
            != capability.checkpoint_id
        ):
            return False
        registry = self.registry
        binding = capability.binding
        scope = binding.scope.conversation
        async with registry._transaction():
            row = await registry._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                (scope.tenant_id, binding.scope.execution_id),
            )
            if (
                row is None
                or _scope(row["scope"]) != binding.scope
                or row["state"] != "ACTIVE"
                or row["runtime_id"] != binding.runtime_id
                or row["packet_revision"] != capability.target_packet_revision
                or row["current_context_fingerprint"]
                != capability.target_context_fingerprint
            ):
                return False
            async with self.journal.execution_store.engine.begin() as conn:
                _, record = await self.journal.lock_owner(
                    conn, scope, binding.scope.execution_id
                )
                await self._check_owner(row, record)
                raw = await self.journal.record(
                    conn,
                    scope,
                    binding.scope.execution_id,
                    "WAIT",
                    binding.wait_event_id,
                )
                if (
                    raw is None
                    or raw["phase"] != "CONSUMED"
                    or raw["resume_start"] != "CLAIMED"
                ):
                    return False
                wait = self.journal.wait(raw, row["refresh_count"])
                return (
                    wait.logical_operation_id,
                    wait.attempt,
                    wait.canonical_request_hmac,
                    wait.expected_current_context_fingerprint,
                    wait.original_deadline,
                    wait.checkpoint_ns,
                    wait.checkpoint_id,
                ) == (
                    binding.operation_id,
                    binding.attempt,
                    binding.canonical_request_hmac,
                    binding.current_context_fingerprint,
                    binding.original_deadline,
                    capability.checkpoint_ns,
                    capability.checkpoint_id,
                ) and await self._frame_available(wait)

    async def finish_resume_start(self, capability):
        existing = self._resume_capabilities.pop(
            getattr(capability, "capability_ref", None), None
        )
        if existing is None or existing[0] is not capability or not existing[2]:
            raise PermissionError("MEMORY_WAIT_CONSUMED")
        binding = capability.binding
        async with self.registry._transaction():
            row = await self.registry._one(
                "SELECT state FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                (binding.scope.conversation.tenant_id, binding.scope.execution_id),
            )
            if row is None:
                raise PermissionError("MEMORY_AUTHORITY_UNAVAILABLE")
            async with self.journal.execution_store.engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE agent_memory_context_refresh SET resume_start='DONE' WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='WAIT' AND record_id=:wait AND resume_start='CLAIMED' AND body_ciphertext IS NOT NULL"
                    ),
                    self.journal.key(
                        binding.scope.conversation, binding.scope.execution_id
                    )
                    | {"wait": binding.wait_event_id.encode()},
                )

    async def _abort_expired_pending(self, row, prior):
        registry = self.registry
        key = (row["tenant_id"], row["execution_id"])
        async with self.journal.execution_store.engine.begin() as conn:
            params = self.journal.key(
                _scope(row["scope"]).conversation, row["execution_id"]
            )
            owner = (
                (
                    await conn.execute(
                        text(
                            "SELECT state FROM agent_memory_execution WHERE tenant_id=:tenant AND execution_id=:execution FOR UPDATE"
                        ),
                        params,
                    )
                )
                .mappings()
                .first()
            )
            if owner is not None and owner["state"] != "SCRUBBED":
                await conn.execute(
                    text(
                        "UPDATE agent_memory_context_refresh SET phase='ABORTED',candidate_phase='ABORTED',receipt_code='EXECUTION_EXPIRED',receipt_state='EXPIRED',dispatch_allowed=false,next_wait_event_id=NULL WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='REFRESH' AND record_id=:candidate AND phase IN ('PENDING','SNAPSHOT_APPLIED') AND body_ciphertext IS NOT NULL"
                    ),
                    params | {"candidate": prior["candidate_id"].encode()},
                )
                await conn.execute(
                    text(
                        "UPDATE agent_memory_context_refresh SET phase='ABORTED' WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='WAIT' AND record_id=:wait AND phase IN ('BUILDING','READY') AND body_ciphertext IS NOT NULL"
                    ),
                    params | {"wait": prior["wait_event_id"].encode()},
                )
        await registry.connection.execute(
            registry._sql(
                "UPDATE {resume} SET candidate_phase='ABORTED',result_code='EXECUTION_EXPIRED',receipt_state='EXPIRED',dispatch_allowed=false,authorization_binding=NULL,next_wait_event_id=NULL WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s AND candidate_phase='PENDING'"
            ),
            (*key, prior["resume_request_id"]),
        )
        await registry.connection.execute(
            registry._sql(
                "UPDATE {execution} SET state='EXPIRED',fence_revision=fence_revision+1,pending_resume_request_id=NULL,pending_candidate_digest=NULL,pending_packet_revision=NULL,pending_context_fingerprint=NULL,terminal_reason='EXECUTION_EXPIRED' WHERE tenant_id=%s AND execution_id=%s"
            ),
            key,
        )
        final = await registry._one(
            "SELECT * FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s",
            (*key, prior["resume_request_id"]),
        )
        return self._receipt(final)

    async def resume(self, scope, execution_id, command):
        registry = self.registry
        key = (scope.tenant_id, execution_id)
        receipt_key = _receipt_key("RESUME", command.resume_request_id)
        fingerprint = command.canonical_fingerprint()
        async with registry._transaction():
            row = await registry._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                key,
            )
            if row is None or _scope(row["scope"]).conversation != scope:
                raise PermissionError("CONTEXT_SCOPE_MISMATCH")
            prior = await registry._one(
                "SELECT * FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s",
                (*key, receipt_key),
            )
            if prior is not None:
                if prior["request_hash"] != fingerprint:
                    raise ValueError("MEMORY_RESUME_CONFLICT")
                if prior["candidate_phase"] != "PENDING":
                    return self._receipt(prior)
                if (
                    row["state"] == "REFRESH_PENDING"
                    and int(registry.clock()) >= row["original_deadline"]
                ):
                    return await self._abort_expired_pending(row, prior)
            else:
                if row["refresh_count"] >= 3:
                    raise ValueError("CONTEXT_REFRESH_LIMIT")
                if row["state"] != "WAITING_CONTEXT" or row["wait_status"] != "READY":
                    raise ValueError("MEMORY_WAIT_CONSUMED")
                async with self.journal.execution_store.engine.begin() as conn:
                    owner, record = await self.journal.lock_owner(
                        conn, scope, execution_id
                    )
                    await self._check_owner(row, record)
                    journal = await self.journal.record(
                        conn, scope, execution_id, "WAIT", command.wait_event_id
                    )
                    if journal is None or journal["phase"] != "READY":
                        raise ValueError("MEMORY_WAIT_CONSUMED")
                    wait = self.journal.wait(journal, row["refresh_count"])
                    await self.journal.verify_wait_operation(conn, journal, record)
                    command.validate_binding(
                        wait,
                        scope,
                        execution_id,
                        owner["current_context_fingerprint"],
                        record.context,
                    )
                    if command.mode != ResumeMode.REFRESH:
                        code = (
                            ResumeCode.CPU_CONFIRMED
                            if command.mode == ResumeMode.CPU
                            else ResumeCode.CONTINUATION_AUTH_UNSUPPORTED
                        )
                        return MemoryContextResumeReceipt(
                            code,
                            None,
                            wait.wait_event_id,
                            None,
                            wait.expected_execution_revision,
                            wait.expected_packet_revision,
                            wait.expected_current_context_fingerprint,
                            row["refresh_count"],
                            RefreshState.WAITING_CONTEXT,
                            None,
                            None,
                            False,
                        )
                    validate_refresh_context(
                        record.context,
                        command.refreshed_context,
                        record.deadline_epoch_seconds,
                        int(registry.clock()),
                    )
                context = command.refreshed_context
                packet = context.packet
                count = row["refresh_count"] + 1
                target = _fingerprint(context.metadata())
                ref = "memory-refresh-" + uuid4().hex
                await registry.connection.execute(
                    registry._sql(
                        "INSERT INTO {resume} (tenant_id,execution_id,resume_request_id,request_hash,result_code,receipt_ref,record_kind,candidate_id,wait_event_id,operation_id,attempt,canonical_request_hmac,wait_phase,old_packet_revision,packet_revision,execution_revision,expected_current_context_fingerprint,target_context_fingerprint,candidate_digest,issued_at,expires_at,candidate_phase,current_packet_revision,current_context_fingerprint,refresh_count,receipt_state,dispatch_allowed) VALUES (%s,%s,%s,%s,'MEMORY_REFRESH_PENDING',%s,'RESUME',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s,%s,%s,'REFRESH_PENDING',false)"
                    ),
                    (
                        *key,
                        receipt_key,
                        fingerprint,
                        ref,
                        command.resume_request_id,
                        wait.wait_event_id,
                        wait.logical_operation_id,
                        wait.attempt,
                        wait.canonical_request_hmac,
                        wait.wait_phase.value,
                        wait.expected_packet_revision,
                        packet.packet_revision,
                        wait.expected_execution_revision,
                        wait.expected_current_context_fingerprint,
                        target,
                        context.packet_digest,
                        packet.issued_at,
                        packet.expires_at,
                        wait.expected_packet_revision,
                        wait.expected_current_context_fingerprint,
                        count,
                    ),
                )
                await registry.connection.execute(
                    registry._sql(
                        "UPDATE {execution} SET state='REFRESH_PENDING',pending_resume_request_id=%s,pending_candidate_digest=%s,pending_packet_revision=%s,pending_context_fingerprint=%s,refresh_count=%s,fence_revision=fence_revision+1 WHERE tenant_id=%s AND execution_id=%s"
                    ),
                    (
                        command.resume_request_id,
                        context.packet_digest,
                        packet.packet_revision,
                        target,
                        count,
                        *key,
                    ),
                )
        await self._fault("after_a")
        async with registry._transaction():
            row = await registry._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                key,
            )
            prior = await registry._one(
                "SELECT * FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s",
                (*key, receipt_key),
            )
            if prior["candidate_phase"] != "PENDING":
                return self._receipt(prior)
            if (
                row["state"] == "REFRESH_PENDING"
                and int(registry.clock()) >= row["original_deadline"]
            ):
                return await self._abort_expired_pending(row, prior)
            if (
                row["state"] != "REFRESH_PENDING"
                or row["pending_resume_request_id"] != command.resume_request_id
            ):
                raise PermissionError("ACCESS_REVOKED")
            async with self.journal.execution_store.engine.begin() as conn:
                owner, record = await self.journal.lock_owner(conn, scope, execution_id)
                await self._check_owner(row, record)
                journal = await self.journal.record(
                    conn, scope, execution_id, "WAIT", command.wait_event_id
                )
                wait = self.journal.wait(journal, row["refresh_count"])
                await self.journal.verify_wait_operation(conn, journal, record)
                original = MemoryExecutionContext.from_metadata(
                    self.journal.body(journal)["context"]
                )
                command.validate_binding(
                    wait,
                    scope,
                    execution_id,
                    wait.expected_current_context_fingerprint,
                    original,
                )
                validate_refresh_context(
                    original,
                    command.refreshed_context,
                    record.deadline_epoch_seconds,
                    int(registry.clock()),
                )
                candidate = await self.journal.apply_snapshot(
                    conn,
                    wait,
                    record,
                    command,
                    prior["refresh_count"],
                    prior["receipt_ref"],
                )
                if candidate["phase"] == "PENDING":
                    if int(registry.clock()) >= candidate["expires_at"]:
                        await self._settle_mysql(
                            conn, wait, candidate, "EXPIRED_UNAPPLIED"
                        )
                    else:
                        if (
                            owner["current_context_fingerprint"]
                            != wait.expected_current_context_fingerprint
                        ):
                            raise ValueError("MEMORY_RESUME_CONFLICT")
                        await self.journal.install(conn, wait, candidate)
        await self._fault("after_b")
        async with registry._transaction():
            row = await registry._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                key,
            )
            prior = await registry._one(
                "SELECT * FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s",
                (*key, receipt_key),
            )
            if prior["candidate_phase"] != "PENDING":
                return self._receipt(prior)
            if (
                row["state"] == "REFRESH_PENDING"
                and int(registry.clock()) >= row["original_deadline"]
            ):
                return await self._abort_expired_pending(row, prior)
            async with self.journal.execution_store.engine.begin() as conn:
                owner, record = await self.journal.lock_owner(conn, scope, execution_id)
                await self._check_owner(row, record)
                journal = await self.journal.record(
                    conn, scope, execution_id, "WAIT", command.wait_event_id
                )
                wait = self.journal.wait(journal, row["refresh_count"])
                await self.journal.verify_wait_operation(conn, journal, record)
                candidate = await self.journal.record(
                    conn, scope, execution_id, "REFRESH", command.resume_request_id
                )
                self.journal.body(candidate)
                if candidate["phase"] == "SNAPSHOT_APPLIED":
                    await self.journal.verify_installed_candidate(
                        conn, wait, prior, candidate, owner, record
                    )
                    phase = (
                        "APPLIED_EXPIRED"
                        if int(registry.clock()) >= candidate["expires_at"]
                        else "ACKED"
                    )
                    dispatch_allowed = False
                    successor_allowed = True
                    if phase in {"ACKED", "APPLIED_EXPIRED"}:
                        original_record = replace(
                            record,
                            context=MemoryExecutionContext.from_metadata(
                                self.journal.body(journal)["context"]
                            ),
                        )
                        updated = False
                        if self.binding_updater is not None:
                            updated = (
                                await self.binding_updater(
                                    original_record, record.context
                                )
                                is True
                            )
                            if phase == "ACKED" and not updated:
                                raise PermissionError("MEMORY_AUTHORITY_UNAVAILABLE")
                        elif (
                            phase == "ACKED"
                            and record.runtime_kind == "CUSTOMER_SERVICE"
                            and await self._frame_available(wait)
                        ):
                            raise PermissionError(
                                "MEMORY_REFRESH_CAPABILITY_UNSUPPORTED"
                            )
                        dispatch_allowed = (
                            phase == "ACKED"
                            and updated
                            and await self._frame_available(wait)
                        )
                        successor_allowed = self.binding_updater is None or updated
                    if int(registry.clock()) >= candidate["expires_at"]:
                        phase = "APPLIED_EXPIRED"
                        dispatch_allowed = False
                    await self._settle_mysql(
                        conn,
                        wait,
                        candidate,
                        phase,
                        dispatch_allowed=dispatch_allowed,
                        successor_allowed=successor_allowed,
                    )
                else:
                    phase = candidate["phase"]
                candidate = await self.journal.record(
                    conn, scope, execution_id, "REFRESH", command.resume_request_id
                )
            await self._fault("after_mysql_settlement")
            block_local_ack = False
            if phase == "ACKED":
                if (
                    row["state"] != "REFRESH_PENDING"
                    or row["pending_resume_request_id"] != prior["candidate_id"]
                    or row["pending_candidate_digest"] != prior["candidate_digest"]
                    or row["pending_packet_revision"] != prior["packet_revision"]
                    or row["pending_context_fingerprint"]
                    != prior["target_context_fingerprint"]
                    or row["refresh_count"] != prior["refresh_count"]
                ):
                    raise PermissionError("ACCESS_REVOKED")
                async with self.journal.execution_store.engine.begin() as conn:
                    owner, record = await self.journal.lock_owner(
                        conn, scope, execution_id
                    )
                    try:
                        await self._check_owner(row, record)
                    except PermissionError as error:
                        if str(error) != "EXECUTION_EXPIRED":
                            raise
                    else:
                        raw_wait = await self.journal.record(
                            conn, scope, execution_id, "WAIT", command.wait_event_id
                        )
                        wait = self.journal.wait(raw_wait, row["refresh_count"])
                        candidate = await self.journal.record(
                            conn,
                            scope,
                            execution_id,
                            "REFRESH",
                            command.resume_request_id,
                        )
                        await self.journal.verify_installed_candidate(
                            conn, wait, prior, candidate, owner, record
                        )
                        if candidate["phase"] != "ACKED":
                            raise ValueError("MEMORY_AUTHORITY_UNAVAILABLE")
                        block_local_ack = bool(
                            candidate["dispatch_allowed"]
                        ) and not await self._frame_available(wait)
            final_now = int(registry.clock())
            if final_now >= row["original_deadline"]:
                return await self._abort_expired_pending(row, prior)
            if phase == "ACKED" and final_now >= candidate["expires_at"]:
                block_local_ack = True
            receipt = await self._settle_pg(
                row, prior, phase, candidate, block_local_ack=block_local_ack
            )
        await self._fault("after_c")
        return receipt

    async def _settle_mysql(
        self,
        conn,
        wait,
        candidate,
        phase,
        *,
        dispatch_allowed=False,
        successor_allowed=True,
    ):
        count = candidate["refresh_count"]
        expired = phase != "ACKED"
        state = (
            "ACTIVE"
            if not expired
            else (
                "WAITING_CONTEXT"
                if phase == "EXPIRED_UNAPPLIED" and count < 3
                else "BLOCKED"
            )
        )
        current = (
            candidate["old_packet_revision"]
            if phase == "EXPIRED_UNAPPLIED"
            else candidate["target_packet_revision"]
        )
        fp = (
            candidate["expected_current_context_fingerprint"]
            if phase == "EXPIRED_UNAPPLIED"
            else candidate["target_context_fingerprint"]
        )
        key = self.journal.key(wait.scope, wait.execution_id)
        next_wait = None
        if (
            phase == "APPLIED_EXPIRED"
            and count < 3
            and successor_allowed
            and wait.checkpoint_mode == CheckpointMode.NONE
            and await self._frame_available(wait)
        ):
            next_wait = replace(
                wait,
                wait_event_id="memory-wait-" + uuid4().hex,
                expected_packet_revision=current,
                expected_current_context_fingerprint=fp,
                refresh_count=count,
            )
            state = "WAITING_CONTEXT"
        await self.journal.settle_run_phase(conn, wait, candidate, phase, state)
        if phase in {"ACKED", "APPLIED_EXPIRED"}:
            await conn.execute(
                text(
                    "UPDATE agent_memory_context_refresh SET phase=:phase,resume_start=:start WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='WAIT' AND record_id=:wait AND phase='READY'"
                ),
                key
                | {
                    "phase": "CONSUMED" if phase == "ACKED" else "SUPERSEDED",
                    "start": "READY"
                    if phase == "ACKED"
                    and wait.checkpoint_mode == CheckpointMode.GRAPH
                    and wait.wait_phase.value == "BEFORE_PREPARE"
                    and await self._frame_available(wait)
                    else None,
                    "wait": wait.wait_event_id.encode(),
                },
            )
        if next_wait is not None:
            body = self.journal.body(candidate)
            record = self.journal.execution_store._decode(
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM agent_memory_execution WHERE tenant_id=:tenant AND execution_id=:execution FOR UPDATE"
                        ),
                        key,
                    )
                )
                .mappings()
                .one()
            )
            await self.journal.insert(
                conn,
                next_wait,
                record,
                "WAIT",
                next_wait.wait_event_id,
                self.journal.body(
                    await self.journal.record(
                        conn, wait.scope, wait.execution_id, "WAIT", wait.wait_event_id
                    )
                )
                | {"context": body["context"]},
                {
                    "wait_event_id": next_wait.wait_event_id.encode(),
                    "wait_phase": next_wait.wait_phase.value,
                    "checkpoint_mode": "NONE",
                    "phase": "BUILDING",
                },
            )
            await conn.execute(
                text(
                    "UPDATE agent_memory_context_refresh SET phase='READY' WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='WAIT' AND record_id=:wait"
                ),
                key | {"wait": next_wait.wait_event_id.encode()},
            )
        await conn.execute(
            text(
                "UPDATE agent_memory_context_refresh SET phase=:phase,candidate_phase=:phase,receipt_code=:code,receipt_state=:state,current_packet_revision=:current,current_context_fingerprint=:fp,next_wait_event_id=:next,dispatch_allowed=:dispatch WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='REFRESH' AND record_id=:record"
            ),
            key
            | {
                "phase": phase,
                "code": "CONTEXT_REFRESHED"
                if phase == "ACKED"
                else "MEMORY_REFRESH_PACKET_EXPIRED",
                "state": state,
                "current": current,
                "fp": fp,
                "record": bytes(candidate["record_id"]),
                "next": None if next_wait is None else next_wait.wait_event_id.encode(),
                "dispatch": dispatch_allowed,
            },
        )

    async def _settle_pg(self, row, prior, phase, candidate, *, block_local_ack=False):
        registry = self.registry
        key = (row["tenant_id"], row["execution_id"])
        old = phase == "EXPIRED_UNAPPLIED"
        if block_local_ack:
            phase = "ABORTED"
        state = "BLOCKED" if block_local_ack else candidate["receipt_state"]
        next_wait_id = (
            None
            if block_local_ack or candidate["next_wait_event_id"] is None
            else bytes(candidate["next_wait_event_id"]).decode()
        )
        current = prior["old_packet_revision"] if old else prior["packet_revision"]
        fp = (
            prior["expected_current_context_fingerprint"]
            if old
            else prior["target_context_fingerprint"]
        )
        code = (
            "MEMORY_AUTHORITY_UNAVAILABLE"
            if block_local_ack
            else (
                "CONTEXT_REFRESHED"
                if phase == "ACKED"
                else "MEMORY_REFRESH_PACKET_EXPIRED"
            )
        )
        await registry.connection.execute(
            registry._sql(
                "UPDATE {resume} SET candidate_phase=%s,result_code=%s,receipt_state=%s,current_packet_revision=%s,current_context_fingerprint=%s,authorization_binding=%s,next_wait_event_id=%s,dispatch_allowed=%s WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s"
            ),
            (
                phase,
                code,
                state,
                current,
                fp,
                None
                if old or block_local_ack
                else ("ACKED" if phase == "ACKED" else "ALIGN_ONLY"),
                next_wait_id,
                False if block_local_ack else bool(candidate["dispatch_allowed"]),
                *key,
                prior["resume_request_id"],
            ),
        )
        clear = (
            "wait_event_id=NULL,wait_status=NULL,wait_packet_revision=NULL,wait_context_fingerprint=NULL,wait_phase=NULL,wait_checkpoint_ns=NULL,wait_checkpoint_id=NULL,"
            if phase == "ACKED"
            else ""
        )
        if next_wait_id is not None:
            clear = "wait_event_id=%s,wait_status='READY',wait_packet_revision=%s,wait_context_fingerprint=%s,wait_checkpoint_ns=NULL,wait_checkpoint_id=NULL,"
        reason = (
            "MEMORY_AUTHORITY_UNAVAILABLE"
            if block_local_ack
            else (
                "CONTEXT_REFRESH_LIMIT"
                if state == "BLOCKED" and prior["refresh_count"] == 3
                else ("CONTINUATION_AUTH_UNSUPPORTED" if state == "BLOCKED" else None)
            )
        )
        await registry.connection.execute(
            registry._sql(
                "UPDATE {execution} SET "
                + clear
                + "state=%s,packet_revision=%s,current_context_fingerprint=%s,packet_expires_at=%s,pending_resume_request_id=NULL,pending_candidate_digest=NULL,pending_packet_revision=NULL,pending_context_fingerprint=NULL,terminal_reason=%s WHERE tenant_id=%s AND execution_id=%s"
            ),
            (
                *((next_wait_id, current, fp) if next_wait_id is not None else ()),
                state,
                current,
                fp,
                row["packet_expires_at"] if old else prior["expires_at"],
                reason,
                *key,
            ),
        )
        final = await registry._one(
            "SELECT * FROM {resume} WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s",
            (*key, prior["resume_request_id"]),
        )
        return self._receipt(final)
