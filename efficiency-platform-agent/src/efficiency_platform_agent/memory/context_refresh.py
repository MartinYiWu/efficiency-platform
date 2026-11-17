"""原执行授权刷新协调器；不授予实际发送能力。"""

from dataclasses import asdict, replace
from uuid import uuid4

from sqlalchemy import text

from efficiency_platform_agent.core.memory_execution import MemoryExecutionContext
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
    def __init__(self, registry, journal, *, fault_hook=None):
        self.registry, self.journal = registry, journal
        self.fault_hook = fault_hook

    async def begin_wait_intent(self, scope, runtime_id, operation_id, attempt, phase):
        registry = self.registry
        key = (scope.conversation.tenant_id, scope.execution_id)
        async with registry._transaction():
            row = await registry._one(
                "SELECT * FROM {execution} WHERE tenant_id=%s AND execution_id=%s FOR UPDATE",
                key,
            )
            if (
                row is None
                or _scope(row["scope"]) != scope
                or row["runtime_id"] != runtime_id
            ):
                raise PermissionError("CONTEXT_SCOPE_MISMATCH")
            if row["checkpoint_mode"] != "NONE":
                raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
            if row["state"] not in {"ACTIVE", "WAITING_CONTEXT"}:
                raise PermissionError("ACCESS_REVOKED")
            async with self.journal.execution_store.engine.begin() as conn:
                owner, record = await self.journal.lock_owner(
                    conn, scope.conversation, scope.execution_id
                )
                await self._check_owner(row, record)
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
                    None,
                    attempt,
                    None,
                    None,
                    CheckpointMode.NONE,
                    None,
                    None,
                    phase,
                    record.deadline_epoch_seconds,
                    row["refresh_count"],
                )
                existing = await self.journal.record(
                    conn, scope.conversation, scope.execution_id, "WAIT", wait_id
                )
                if existing is None:
                    await self.journal.insert(
                        conn,
                        wait,
                        record,
                        "WAIT",
                        wait_id,
                        {"context": record.context.metadata()},
                        {
                            "wait_event_id": wait_id.encode(),
                            "wait_phase": phase.value,
                            "checkpoint_mode": "NONE",
                            "phase": "BUILDING",
                        },
                    )
                elif self.journal.wait(existing, row["refresh_count"]) != wait:
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
        else:
            raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")

    async def finish_wait(self, scope, execution_id, wait_id):
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
                wait = self.journal.wait(journal, row["refresh_count"])
                if wait.checkpoint_mode != CheckpointMode.NONE:
                    raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
                await conn.execute(
                    text(
                        "UPDATE agent_memory_context_refresh SET phase='READY' WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='WAIT' AND record_id=:wait AND phase='BUILDING'"
                    ),
                    self.journal.key(scope, execution_id) | {"wait": wait_id.encode()},
                )
            await registry.connection.execute(
                registry._sql(
                    "UPDATE {execution} SET wait_status='READY' WHERE tenant_id=%s AND execution_id=%s"
                ),
                key,
            )

    async def get_wait(self, scope, execution_id):
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
            if row["state"] != "WAITING_CONTEXT" or row["wait_status"] != "READY":
                return None
            async with self.journal.execution_store.engine.begin() as conn:
                _, record = await self.journal.lock_owner(conn, scope, execution_id)
                await self._check_owner(row, record)
                journal = await self.journal.record(
                    conn, scope, execution_id, "WAIT", row["wait_event_id"]
                )
                if journal is None or journal["phase"] != "READY":
                    return None
                return self.journal.wait(journal, row["refresh_count"])

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
            async with self.journal.execution_store.engine.begin() as conn:
                owner, record = await self.journal.lock_owner(conn, scope, execution_id)
                await self._check_owner(row, record)
                journal = await self.journal.record(
                    conn, scope, execution_id, "WAIT", command.wait_event_id
                )
                wait = self.journal.wait(journal, row["refresh_count"])
                candidate = await self.journal.record(
                    conn, scope, execution_id, "REFRESH", command.resume_request_id
                )
                self.journal.body(candidate)
                if candidate["phase"] == "SNAPSHOT_APPLIED":
                    if (
                        owner["current_context_fingerprint"]
                        != prior["target_context_fingerprint"]
                        or record.context != command.refreshed_context
                    ):
                        raise ValueError("MEMORY_AUTHORITY_UNAVAILABLE")
                    phase = (
                        "APPLIED_EXPIRED"
                        if int(registry.clock()) >= candidate["expires_at"]
                        else "ACKED"
                    )
                    await self._settle_mysql(conn, wait, candidate, phase)
                else:
                    phase = candidate["phase"]
            receipt = await self._settle_pg(row, prior, phase)
        await self._fault("after_c")
        return receipt

    async def _settle_mysql(self, conn, wait, candidate, phase):
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
        if phase in {"ACKED", "APPLIED_EXPIRED"}:
            await conn.execute(
                text(
                    "UPDATE agent_memory_context_refresh SET phase=:phase,resume_start=:start WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='WAIT' AND record_id=:wait AND phase='READY'"
                ),
                key
                | {
                    "phase": "CONSUMED" if phase == "ACKED" else "SUPERSEDED",
                    "start": "READY" if phase == "ACKED" else None,
                    "wait": wait.wait_event_id.encode(),
                },
            )
        await conn.execute(
            text(
                "UPDATE agent_memory_context_refresh SET phase=:phase,candidate_phase=:phase,receipt_code=:code,receipt_state=:state,current_packet_revision=:current,current_context_fingerprint=:fp,dispatch_allowed=false WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='REFRESH' AND record_id=:record"
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
            },
        )

    async def _settle_pg(self, row, prior, phase):
        registry = self.registry
        key = (row["tenant_id"], row["execution_id"])
        old = phase == "EXPIRED_UNAPPLIED"
        state = (
            "ACTIVE"
            if phase == "ACKED"
            else (
                "WAITING_CONTEXT" if old and prior["refresh_count"] < 3 else "BLOCKED"
            )
        )
        current = prior["old_packet_revision"] if old else prior["packet_revision"]
        fp = (
            prior["expected_current_context_fingerprint"]
            if old
            else prior["target_context_fingerprint"]
        )
        code = (
            "CONTEXT_REFRESHED" if phase == "ACKED" else "MEMORY_REFRESH_PACKET_EXPIRED"
        )
        await registry.connection.execute(
            registry._sql(
                "UPDATE {resume} SET candidate_phase=%s,result_code=%s,receipt_state=%s,current_packet_revision=%s,current_context_fingerprint=%s,authorization_binding=%s,dispatch_allowed=false WHERE tenant_id=%s AND execution_id=%s AND resume_request_id=%s"
            ),
            (
                phase,
                code,
                state,
                current,
                fp,
                None if old else ("ACKED" if phase == "ACKED" else "ALIGN_ONLY"),
                *key,
                prior["resume_request_id"],
            ),
        )
        clear = (
            "wait_event_id=NULL,wait_status=NULL,wait_packet_revision=NULL,wait_context_fingerprint=NULL,wait_phase=NULL,wait_checkpoint_ns=NULL,wait_checkpoint_id=NULL,"
            if phase == "ACKED"
            else ""
        )
        reason = (
            "CONTEXT_REFRESH_LIMIT"
            if state == "BLOCKED" and prior["refresh_count"] == 3
            else ("CONTINUATION_AUTH_UNSUPPORTED" if state == "BLOCKED" else None)
        )
        await registry.connection.execute(
            registry._sql(
                "UPDATE {execution} SET "
                + clear
                + "state=%s,packet_revision=%s,current_context_fingerprint=%s,packet_expires_at=%s,pending_resume_request_id=NULL,pending_candidate_digest=NULL,pending_packet_revision=NULL,pending_context_fingerprint=NULL,terminal_reason=%s WHERE tenant_id=%s AND execution_id=%s"
            ),
            (
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
