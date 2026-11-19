"""单库刷新journal适配器；原财务与请求锚永久保留。"""

import base64
import hashlib
import json
from dataclasses import asdict, replace

from sqlalchemy import text

from efficiency_platform_agent.contracts.context_control import ContextManifestModel
from efficiency_platform_agent.core.context_ports import ContextOperation
from efficiency_platform_agent.core.memory import ConversationScope, ExecutionScope
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionContext,
    memory_operation_deadline_matches,
)
from efficiency_platform_agent.core.memory_refresh import (
    CheckpointMode,
    MemoryContextWait,
    WaitPhase,
)

from .memory_cipher import SealedMemorySnapshot
from .memory_execution import _fingerprint

_KEY = "tenant_id=:tenant AND execution_id=:execution"


def _journal_binding(row):
    fields = (
        "task_id",
        "request_hash",
        "request_fingerprint",
        "semantic_input_hash",
        "operation_id",
        "attempt",
        "canonical_request_hmac",
        "stage_id",
        "stage_slot",
        "execution_revision",
        "original_deadline",
        "old_packet_revision",
        "expected_current_context_fingerprint",
        "wait_event_id",
        "resume_request_id",
        "wait_phase",
        "checkpoint_mode",
        "target_packet_revision",
        "target_context_fingerprint",
        "target_snapshot_hash",
        "candidate_digest",
        "issued_at",
        "expires_at",
        "pg_ordinal",
        "sent_packet_revision",
        "sent_packet_digest",
        "send_permit_hash",
        "result_hash",
    )
    return _fingerprint(
        {
            key: bytes(value).hex()
            if isinstance(value, (bytes, bytearray, memoryview))
            else value
            for key in fields
            for value in (row.get(key),)
        }
    )


class MySqlMemoryContextRefreshStore:
    def __init__(self, execution_store):
        if not execution_store.refresh_schema_required:
            raise PermissionError("MEMORY_REFRESH_SCHEMA_REQUIRED")
        self.execution_store = execution_store

    async def _run_row(self, connection, record):
        scope = record.context.packet.scope
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT request_id,status,version,state_json FROM agent_run WHERE tenant_id=:tenant AND run_id=:runtime FOR UPDATE"
                    ),
                    {"tenant": scope.tenant_id, "runtime": record.runtime_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        raw = (
            json.loads(row["state_json"])
            if isinstance(row["state_json"], str)
            else row["state_json"]
        )
        request = raw["request"]
        metadata = request["metadata"]
        if (
            raw.get("memory_scrubbed") is True
            or raw["run_id"] != record.runtime_id
            or request["tenant_id"] != scope.tenant_id
            or request["user_id"] != scope.user_id
            or request["request_id"] != row["request_id"]
            or metadata.get("context_scope") != asdict(scope)
            or raw["version"] != row["version"]
            or str(row["status"]).upper() != "RUNNING"
            or str(raw["status"]).upper() != "RUNNING"
        ):
            raise ValueError("MEMORY_RESUME_CONFLICT")
        envelope = metadata["memory_execution"]
        if envelope["execution_id"] != record.context.packet.execution_id:
            raise ValueError("MEMORY_RESUME_CONFLICT")
        context = MemoryExecutionContext.from_metadata(
            json.loads(
                self.execution_store.cipher.open(
                    scope.tenant_id,
                    record.context.packet.execution_id,
                    record.runtime_id,
                    SealedMemorySnapshot(
                        base64.b64decode(envelope["ciphertext"], validate=True),
                        base64.b64decode(envelope["nonce"], validate=True),
                        envelope["key_version"],
                    ),
                )
            )
        )
        return row, raw, context

    @staticmethod
    def _run_anchor(raw):
        request = raw["request"]
        return {
            "request_id": request["request_id"],
            "request_fields_hash": _fingerprint(
                {key: value for key, value in request.items() if key != "metadata"}
            ),
            "context_request_fingerprint": request["metadata"].get(
                "context_request_fingerprint"
            ),
        }

    async def run_anchor(self, connection, record):
        _, raw, context = await self._run_row(connection, record)
        if context != record.context:
            raise ValueError("MEMORY_RESUME_CONFLICT")
        return self._run_anchor(raw)

    async def _install_run_snapshot(self, connection, wait, record, context):
        row, raw, current = await self._run_row(connection, record)
        original_wait = await self.record(
            connection, wait.scope, wait.execution_id, "WAIT", wait.wait_event_id
        )
        body = self.body(original_wait)
        if (
            body.get("run_anchor") != self._run_anchor(raw)
            or raw["request"]["metadata"].get("context_request_fingerprint")
            != record.request_fingerprint
            or current != MemoryExecutionContext.from_metadata(body["context"])
            or _fingerprint(current.metadata())
            != wait.expected_current_context_fingerprint
        ):
            raise ValueError("MEMORY_RESUME_CONFLICT")
        sealed = self.execution_store.cipher.seal(
            wait.scope.tenant_id,
            wait.execution_id,
            record.runtime_id,
            json.dumps(
                context.metadata(), ensure_ascii=False, separators=(",", ":")
            ).encode(),
            key_version=record.key_version,
        )
        raw["request"]["metadata"]["memory_execution"] = {
            "execution_id": wait.execution_id,
            "key_version": sealed.key_version,
            "nonce": base64.b64encode(sealed.nonce).decode("ascii"),
            "ciphertext": base64.b64encode(sealed.ciphertext).decode("ascii"),
        }
        raw["request"]["metadata"]["memory_execution_phase"] = "REFRESH_PENDING"
        raw["version"] = row["version"] + 1
        changed = await connection.execute(
            text(
                "UPDATE agent_run SET state_json=CAST(:body AS JSON),version=version+1 WHERE tenant_id=:tenant AND run_id=:runtime AND version=:version"
            ),
            {
                "tenant": wait.scope.tenant_id,
                "runtime": record.runtime_id,
                "version": row["version"],
                "body": json.dumps(raw, ensure_ascii=False, separators=(",", ":")),
            },
        )
        if changed.rowcount != 1:
            raise ValueError("MEMORY_RESUME_CONFLICT")

    async def settle_run_phase(self, connection, wait, candidate, phase, state):
        if wait.scope.domain != "operations":
            return
        _, record = await self.lock_owner(connection, wait.scope, wait.execution_id)
        row, raw, current = await self._run_row(connection, record)
        if (
            current != record.context
            or raw["request"]["metadata"].get("context_request_fingerprint")
            != record.request_fingerprint
        ):
            raise ValueError("MEMORY_RESUME_CONFLICT")
        raw["request"]["metadata"]["memory_execution_phase"] = (
            "AUTH_READY"
            if phase == "ACKED"
            else ("WAITING_CONTEXT" if state == "WAITING_CONTEXT" else "BLOCKED")
        )
        raw["version"] = row["version"] + 1
        changed = await connection.execute(
            text(
                "UPDATE agent_run SET state_json=CAST(:body AS JSON),version=version+1 WHERE tenant_id=:tenant AND run_id=:runtime AND version=:version"
            ),
            {
                "tenant": wait.scope.tenant_id,
                "runtime": record.runtime_id,
                "version": row["version"],
                "body": json.dumps(raw, ensure_ascii=False, separators=(",", ":")),
            },
        )
        if changed.rowcount != 1:
            raise ValueError("MEMORY_RESUME_CONFLICT")

    async def verify_installed_candidate(
        self, connection, wait, prior, candidate, owner, record
    ):
        if candidate["phase"] not in {"SNAPSHOT_APPLIED", "ACKED"}:
            raise ValueError("MEMORY_AUTHORITY_UNAVAILABLE")
        body = self.body(candidate)
        original_wait = await self.record(
            connection, wait.scope, wait.execution_id, "WAIT", wait.wait_event_id
        )
        if original_wait is None or original_wait["phase"] != (
            "CONSUMED" if candidate["phase"] == "ACKED" else "READY"
        ):
            raise ValueError("MEMORY_AUTHORITY_UNAVAILABLE")
        frozen = self.wait(original_wait, prior["refresh_count"])
        await self.verify_wait_operation(connection, original_wait, record)
        if frozen != wait:
            raise ValueError("MEMORY_RESUME_CONFLICT")
        checks = {
            "record_id": prior["candidate_id"].encode(),
            "resume_request_id": prior["candidate_id"].encode(),
            "wait_event_id": wait.wait_event_id.encode(),
            "runtime_id": record.runtime_id.encode(),
            "task_id": wait.task_id.encode(),
            "request_hash": prior["request_hash"],
            "request_fingerprint": record.request_fingerprint,
            "operation_id": prior["operation_id"].encode(),
            "attempt": prior["attempt"],
            "canonical_request_hmac": prior["canonical_request_hmac"],
            "stage_id": None if wait.stage_id is None else wait.stage_id.encode(),
            "stage_slot": wait.stage_slot,
            "semantic_input_hash": wait.semantic_input_hash,
            "wait_phase": prior["wait_phase"],
            "old_packet_revision": prior["old_packet_revision"],
            "execution_revision": prior["execution_revision"],
            "original_deadline": record.deadline_epoch_seconds,
            "expected_current_context_fingerprint": prior[
                "expected_current_context_fingerprint"
            ],
            "target_packet_revision": prior["packet_revision"],
            "target_context_fingerprint": prior["target_context_fingerprint"],
            "candidate_digest": prior["candidate_digest"],
            "issued_at": prior["issued_at"],
            "expires_at": prior["expires_at"],
            "pg_ordinal": prior["refresh_count"],
            "refresh_count": prior["refresh_count"],
            "key_version": record.key_version,
        }
        if any(candidate[key] != value for key, value in checks.items()):
            raise ValueError("MEMORY_RESUME_CONFLICT")
        if (
            wait.logical_operation_id != prior["operation_id"]
            or wait.attempt != prior["attempt"]
            or wait.canonical_request_hmac != prior["canonical_request_hmac"]
            or wait.wait_phase.value != prior["wait_phase"]
            or wait.expected_packet_revision != prior["old_packet_revision"]
            or wait.expected_current_context_fingerprint
            != prior["expected_current_context_fingerprint"]
        ):
            raise ValueError("MEMORY_RESUME_CONFLICT")
        context = MemoryExecutionContext.from_metadata(body["context"])
        if (
            context != record.context
            or owner["current_context_fingerprint"]
            != prior["target_context_fingerprint"]
            or _fingerprint(context.metadata()) != prior["target_context_fingerprint"]
            or record.context.packet.packet_revision != prior["packet_revision"]
            or record.context.packet_digest != prior["candidate_digest"]
            or record.key_version != owner["key_version"]
            or bytes.fromhex(body["snapshot_nonce"]) != bytes(owner["snapshot_nonce"])
            or bytes.fromhex(body["snapshot_ciphertext"])
            != bytes(owner["snapshot_ciphertext"])
            or hashlib.sha256(
                bytes(owner["snapshot_nonce"]) + bytes(owner["snapshot_ciphertext"])
            ).hexdigest()
            != candidate["target_snapshot_hash"]
        ):
            raise ValueError("MEMORY_AUTHORITY_UNAVAILABLE")
        if record.runtime_kind == "OPERATIONS":
            _, raw, current = await self._run_row(connection, record)
            original_body = self.body(original_wait)
            if (
                current != record.context
                or original_body.get("run_anchor") != self._run_anchor(raw)
                or raw["request"]["metadata"].get("context_request_fingerprint")
                != record.request_fingerprint
                or raw["request"]["metadata"]["memory_execution"]["key_version"]
                != record.key_version
            ):
                raise ValueError("MEMORY_RESUME_CONFLICT")

    @staticmethod
    def key(scope: ConversationScope, execution_id: str):
        return {"tenant": scope.tenant_id.encode(), "execution": execution_id.encode()}

    async def lock_owner(self, connection, scope, execution_id):
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT * FROM agent_memory_execution WHERE "
                        + _KEY
                        + " FOR UPDATE"
                    ),
                    self.key(scope, execution_id),
                )
            )
            .mappings()
            .first()
        )
        if row is None or row["state"] != "ACTIVE":
            raise PermissionError("ACCESS_REVOKED")
        record = self.execution_store._decode(row)
        if record.context.packet.scope != scope:
            raise PermissionError("CONTEXT_SCOPE_MISMATCH")
        return row, record

    async def record(self, connection, scope, execution_id, kind, record_id):
        return (
            (
                await connection.execute(
                    text(
                        "SELECT * FROM agent_memory_context_refresh WHERE "
                        + _KEY
                        + " AND record_kind=:kind AND record_id=:record FOR UPDATE"
                    ),
                    self.key(scope, execution_id)
                    | {"kind": kind, "record": record_id.encode()},
                )
            )
            .mappings()
            .first()
        )

    async def verify_operation(
        self,
        connection,
        wait,
        record,
        *,
        operation_scope,
        manifest_hash=None,
        require_not_sent=True,
    ):
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT o.input_hash,o.status,o.deadline,o.latest_attempt,m.metadata_json FROM agent_context_operation o JOIN agent_context_manifest m USING(tenant_id,task_id,execution_id,operation_id) WHERE o.tenant_id=:tenant AND o.execution_id=:execution AND o.task_id=:task AND o.operation_id=:operation AND m.attempt=:attempt FOR UPDATE"
                    ),
                    self.key(wait.scope, wait.execution_id)
                    | {
                        "task": wait.task_id.encode(),
                        "operation": wait.logical_operation_id.encode(),
                        "attempt": wait.attempt,
                    },
                )
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or row["status"]
            not in (
                {"NOT_SENT"}
                if require_not_sent
                else {"NOT_SENT", "SENT", "SUCCEEDED", "UNKNOWN"}
            )
            or row["latest_attempt"] != wait.attempt
            or row["input_hash"] != wait.canonical_request_hmac
            or row["deadline"] != wait.original_deadline
        ):
            raise PermissionError("MEMORY_AUTHORITY_UNAVAILABLE")
        manifest = ContextManifestModel.model_validate_json(
            row["metadata_json"]
        ).to_core()
        packet = record.context.packet
        if (
            manifest.scope != operation_scope
            or manifest.node_id != operation_scope.subtask_id
            or (
                operation_scope.conversation,
                operation_scope.task_id,
                operation_scope.execution_id,
            )
            != (packet.scope, packet.task_id, packet.execution_id)
            or not any(
                (grant.node_id, grant.execution_agent_id, grant.purpose)
                == (
                    operation_scope.subtask_id,
                    operation_scope.execution_agent_id,
                    operation_scope.purpose,
                )
                for grant in record.context.execution_grants
            )
            or operation_scope.execution_agent_id not in record.context.policy.agent_ids
            or manifest.operation_id != wait.logical_operation_id
            or manifest.attempt != wait.attempt
            or manifest.canonical_request_hmac != wait.canonical_request_hmac
            or manifest.packet_id != packet.packet_id
            or not set(manifest.safety_dependencies).issubset(
                packet.safety_dependencies
            )
        ):
            raise PermissionError("CONTEXT_SCOPE_MISMATCH")
        digest = _fingerprint(
            json.loads(ContextManifestModel.from_core(manifest).model_dump_json())
        )
        if manifest_hash is not None and digest != manifest_hash:
            raise ValueError("MEMORY_RESUME_CONFLICT")
        if manifest_hash is None and manifest.packet_revision != packet.packet_revision:
            operation = ContextOperation(
                manifest.operation_id, manifest.attempt, wait.original_deadline, False
            )
            if not await self._revision_chain_locked(
                connection,
                record,
                manifest.packet_revision,
                _fingerprint(record.context.metadata()),
                operation=operation,
                input_hash=manifest.canonical_request_hmac,
            ):
                raise PermissionError("MEMORY_AUTHORITY_UNAVAILABLE")
        return {"operation_scope": asdict(operation_scope), "manifest_hash": digest}

    async def verify_wait_operation(
        self, connection, raw_wait, record, *, require_not_sent=True
    ):
        if raw_wait["wait_phase"] == "BEFORE_PREPARE":
            return
        body = self.body(raw_wait)
        if set(body.get("operation_scope", {})) != {
            "conversation",
            "task_id",
            "execution_id",
            "subtask_id",
            "purpose",
            "execution_agent_id",
        } or not isinstance(body.get("manifest_hash"), str):
            raise PermissionError("MEMORY_AUTHORITY_UNAVAILABLE")
        value = dict(body["operation_scope"])
        value["conversation"] = ConversationScope(**value["conversation"])
        operation_scope = ExecutionScope(**value)
        return await self.verify_operation(
            connection,
            self.wait(raw_wait, 0, draft=raw_wait["phase"] == "BUILDING"),
            record,
            operation_scope=operation_scope,
            manifest_hash=body["manifest_hash"],
            require_not_sent=require_not_sent,
        )

    def body(self, row):
        if row["body_ciphertext"] is None:
            raise PermissionError("ACCESS_REVOKED")
        scope = tuple(
            bytes(row[key]).decode()
            if key in {"tenant_id", "user_id", "session_id"} and row[key] is not None
            else row[key]
            for key in (
                "tenant_id",
                "user_id",
                "domain",
                "top_level_agent_id",
                "session_kind",
                "session_id",
            )
        )
        return json.loads(
            self.execution_store.cipher.open_journal(
                scope,
                bytes(row["execution_id"]).decode(),
                bytes(row["runtime_id"]).decode(),
                bytes(row["record_id"]).decode(),
                row["record_kind"],
                SealedMemorySnapshot(
                    bytes(row["body_ciphertext"]),
                    bytes(row["body_nonce"]),
                    row["key_version"],
                ),
                binding=_journal_binding(row),
            )
        )

    async def insert(self, connection, wait, record, kind, record_id, body, extra):
        scope = wait.scope
        data = {
            "tenant_id": scope.tenant_id.encode(),
            "execution_id": wait.execution_id.encode(),
            "record_kind": kind,
            "record_id": record_id.encode(),
            "runtime_id": wait.runtime_id.encode(),
            "task_id": wait.task_id.encode(),
            "user_id": scope.user_id.encode(),
            "domain": scope.domain,
            "top_level_agent_id": scope.top_level_agent_id,
            "session_kind": scope.session_kind,
            "session_id": None
            if scope.session_id is None
            else scope.session_id.encode(),
            "request_hash": _fingerprint(body),
            "request_fingerprint": wait.operation_hash,
            "semantic_input_hash": wait.semantic_input_hash,
            "operation_id": wait.logical_operation_id.encode(),
            "attempt": wait.attempt,
            "canonical_request_hmac": wait.canonical_request_hmac,
            "stage_id": None if wait.stage_id is None else wait.stage_id.encode(),
            "stage_slot": wait.stage_slot,
            "execution_revision": wait.expected_execution_revision,
            "original_deadline": wait.original_deadline,
            "old_packet_revision": wait.expected_packet_revision,
            "expected_current_context_fingerprint": wait.expected_current_context_fingerprint,
        } | extra
        sealed = self.execution_store.cipher.seal_journal(
            tuple(asdict(scope).values()),
            wait.execution_id,
            wait.runtime_id,
            record_id,
            kind,
            json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(),
            binding=_journal_binding(data),
            key_version=record.key_version,
        )
        data.update(
            body_ciphertext=sealed.ciphertext,
            body_nonce=sealed.nonce,
            key_version=sealed.key_version,
        )
        columns = ",".join(data)
        await connection.execute(
            text(
                "INSERT INTO agent_memory_context_refresh ("
                + columns
                + ") VALUES ("
                + ",".join(":" + name for name in data)
                + ")"
            ),
            data,
        )

    def wait(self, row, refresh_count, *, checkpoint=None, draft=False):
        scope = ConversationScope(
            *(
                bytes(row[key]).decode()
                if key in {"tenant_id", "user_id", "session_id"}
                and row[key] is not None
                else row[key]
                for key in (
                    "tenant_id",
                    "user_id",
                    "domain",
                    "top_level_agent_id",
                    "session_kind",
                    "session_id",
                )
            )
        )
        self.body(row)
        decode = lambda key: None if row[key] is None else bytes(row[key]).decode()
        return MemoryContextWait(
            "memory-context-wait/1",
            decode("wait_event_id"),
            decode("runtime_id"),
            decode("task_id"),
            decode("execution_id"),
            scope,
            row["old_packet_revision"],
            row["execution_revision"],
            row["expected_current_context_fingerprint"],
            row["request_fingerprint"],
            decode("operation_id"),
            row["semantic_input_hash"],
            row["canonical_request_hmac"],
            row["attempt"],
            decode("stage_id"),
            row["stage_slot"],
            CheckpointMode.NONE if draft else CheckpointMode(row["checkpoint_mode"]),
            None
            if draft
            else (decode("checkpoint_ns") if checkpoint is None else checkpoint[0]),
            None
            if draft
            else (decode("checkpoint_id") if checkpoint is None else checkpoint[1]),
            WaitPhase(row["wait_phase"]),
            row["original_deadline"],
            refresh_count,
        )

    async def apply_snapshot(
        self, connection, wait, record, command, ordinal, receipt_ref
    ):
        existing = await self.record(
            connection,
            wait.scope,
            wait.execution_id,
            "REFRESH",
            command.resume_request_id,
        )
        if existing is not None:
            if existing["request_hash"] != command.canonical_fingerprint():
                raise ValueError("MEMORY_RESUME_CONFLICT")
            self.body(existing)
            return existing
        context = command.refreshed_context
        sealed = self.execution_store.cipher.seal(
            wait.scope.tenant_id,
            wait.execution_id,
            wait.runtime_id,
            json.dumps(
                context.metadata(), ensure_ascii=False, separators=(",", ":")
            ).encode(),
            key_version=record.key_version,
        )
        target = _fingerprint(context.metadata())
        packet = context.packet
        await self.insert(
            connection,
            wait,
            record,
            "REFRESH",
            command.resume_request_id,
            {
                "command_fingerprint": command.canonical_fingerprint(),
                "context": context.metadata(),
                "snapshot_ciphertext": sealed.ciphertext.hex(),
                "snapshot_nonce": sealed.nonce.hex(),
            },
            {
                "request_hash": command.canonical_fingerprint(),
                "wait_event_id": wait.wait_event_id.encode(),
                "resume_request_id": command.resume_request_id.encode(),
                "wait_phase": wait.wait_phase.value,
                "target_packet_revision": packet.packet_revision,
                "target_context_fingerprint": target,
                "target_snapshot_hash": hashlib.sha256(
                    sealed.nonce + sealed.ciphertext
                ).hexdigest(),
                "candidate_digest": context.packet_digest,
                "issued_at": packet.issued_at,
                "expires_at": packet.expires_at,
                "pg_ordinal": ordinal,
                "phase": "PENDING",
                "candidate_phase": "PENDING",
                "receipt_code": "MEMORY_REFRESH_PENDING",
                "receipt_ref": receipt_ref.encode(),
                "receipt_state": "REFRESH_PENDING",
                "current_packet_revision": wait.expected_packet_revision,
                "current_context_fingerprint": wait.expected_current_context_fingerprint,
                "refresh_count": ordinal,
            },
        )
        return await self.record(
            connection,
            wait.scope,
            wait.execution_id,
            "REFRESH",
            command.resume_request_id,
        )

    async def install(self, connection, wait, candidate):
        body = self.body(candidate)
        await connection.execute(
            text(
                "UPDATE agent_memory_execution SET snapshot_ciphertext=:ciphertext,snapshot_nonce=:nonce,current_context_fingerprint=:current WHERE "
                + _KEY
            ),
            self.key(wait.scope, wait.execution_id)
            | {
                "ciphertext": bytes.fromhex(body["snapshot_ciphertext"]),
                "nonce": bytes.fromhex(body["snapshot_nonce"]),
                "current": candidate["target_context_fingerprint"],
            },
        )
        if wait.scope.domain == "operations":
            original_wait = await self.record(
                connection, wait.scope, wait.execution_id, "WAIT", wait.wait_event_id
            )
            original = MemoryExecutionContext.from_metadata(
                self.body(original_wait)["context"]
            )
            owner = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM agent_memory_execution WHERE "
                            + _KEY
                            + " FOR UPDATE"
                        ),
                        self.key(wait.scope, wait.execution_id),
                    )
                )
                .mappings()
                .one()
            )
            record = self.execution_store._decode(owner)
            await self._install_run_snapshot(
                connection,
                wait,
                replace(record, context=original),
                MemoryExecutionContext.from_metadata(body["context"]),
            )
        await connection.execute(
            text(
                "UPDATE agent_memory_context_refresh SET phase='SNAPSHOT_APPLIED' WHERE "
                + _KEY
                + " AND record_kind='REFRESH' AND record_id=:record AND phase='PENDING'"
            ),
            self.key(wait.scope, wait.execution_id)
            | {"record": bytes(candidate["record_id"])},
        )

    async def _revision_chain_locked(
        self,
        connection,
        record,
        revision,
        fingerprint,
        *,
        operation=None,
        input_hash=None,
    ):
        packet = record.context.packet
        if revision == packet.packet_revision:
            return True
        current_revision = packet.packet_revision
        previous_wait_id = None
        for depth in range(3):
            params = self.key(packet.scope, packet.execution_id) | {
                "revision": current_revision,
                "fp": fingerprint,
                "deadline": record.deadline_epoch_seconds,
            }
            same_operation = ""
            if operation is not None:
                same_operation = " AND operation_id=:operation AND attempt=:attempt AND canonical_request_hmac=:hmac"
                params.update(
                    operation=operation.operation_id.encode(),
                    attempt=operation.attempt,
                    hmac=input_hash,
                )
            candidates = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM agent_memory_context_refresh WHERE "
                            + _KEY
                            + " AND record_kind='REFRESH' AND phase IN ('ACKED','APPLIED_EXPIRED') AND target_packet_revision=:revision AND target_context_fingerprint=:fp AND original_deadline=:deadline"
                            + same_operation
                            + " FOR UPDATE"
                        ),
                        params,
                    )
                )
                .mappings()
                .all()
            )
            if len(candidates) != 1:
                return False
            candidate = candidates[0]
            if depth == 0 and (
                candidate["phase"] != "ACKED"
                or (operation is not None and not candidate["dispatch_allowed"])
            ):
                return False
            if candidate["key_version"] != record.key_version:
                return False
            context = MemoryExecutionContext.from_metadata(
                self.body(candidate)["context"]
            )
            if (
                context.packet.packet_revision != current_revision
                or _fingerprint(context.metadata()) != fingerprint
                or context.packet_digest != candidate["candidate_digest"]
                or context.semantic_snapshot_digest
                != record.context.semantic_snapshot_digest
                or replace(
                    context, packet=packet, packet_digest=record.context.packet_digest
                )
                != record.context
                or replace(
                    context.packet,
                    packet_revision=packet.packet_revision,
                    execution_revision=packet.execution_revision,
                    issued_at=packet.issued_at,
                    expires_at=packet.expires_at,
                )
                != packet
            ):
                return False
            wait_id = bytes(candidate["wait_event_id"]).decode()
            wait = await self.record(
                connection, packet.scope, packet.execution_id, "WAIT", wait_id
            )
            expected_phase = (
                "CONSUMED" if candidate["phase"] == "ACKED" else "SUPERSEDED"
            )
            if (
                wait is None
                or wait["phase"] != expected_phase
                or wait["operation_id"] != candidate["operation_id"]
                or wait["attempt"] != candidate["attempt"]
                or wait["canonical_request_hmac"] != candidate["canonical_request_hmac"]
                or wait["stage_id"] != candidate["stage_id"]
                or wait["stage_slot"] != candidate["stage_slot"]
            ):
                return False
            old = MemoryExecutionContext.from_metadata(self.body(wait)["context"])
            await self.verify_wait_operation(
                connection, wait, record, require_not_sent=False
            )
            if (
                _fingerprint(old.metadata())
                != candidate["expected_current_context_fingerprint"]
                or old.packet.packet_revision != candidate["old_packet_revision"]
                or old.semantic_snapshot_digest != context.semantic_snapshot_digest
                or replace(context, packet=old.packet, packet_digest=old.packet_digest)
                != old
            ):
                return False
            if candidate["phase"] == "APPLIED_EXPIRED" and (
                candidate["next_wait_event_id"] is None
                or previous_wait_id is None
                or bytes(candidate["next_wait_event_id"]).decode() != previous_wait_id
            ):
                return False
            previous_wait_id = wait_id
            current_revision, fingerprint = (
                candidate["old_packet_revision"],
                candidate["expected_current_context_fingerprint"],
            )
            if current_revision == revision:
                return True
        return False

    async def manifest_authorized_locked(
        self, connection, manifest, operation, record, current_fingerprint
    ):
        packet = record.context.packet
        if (
            manifest.scope.conversation != packet.scope
            or manifest.scope.task_id != packet.task_id
            or manifest.scope.execution_id != packet.execution_id
            or manifest.operation_id != operation.operation_id
            or manifest.attempt != operation.attempt
            or operation.memory_disabled
            or not memory_operation_deadline_matches(
                manifest.node_id,
                operation.deadline_epoch_seconds,
                record.deadline_epoch_seconds,
            )
            or manifest.packet_id != packet.packet_id
            or manifest.packet_revision is None
        ):
            return False
        saved = (
            await connection.execute(
                text(
                    "SELECT metadata_json FROM agent_context_manifest WHERE tenant_id=:tenant AND execution_id=:execution AND task_id=:task AND operation_id=:operation AND attempt=:attempt FOR UPDATE"
                ),
                self.key(packet.scope, packet.execution_id)
                | {
                    "task": packet.task_id.encode(),
                    "operation": manifest.operation_id.encode(),
                    "attempt": manifest.attempt,
                },
            )
        ).scalar_one_or_none()
        if (
            saved is None
            or ContextManifestModel.model_validate_json(saved).to_core() != manifest
        ):
            return False
        return await self._revision_chain_locked(
            connection,
            record,
            manifest.packet_revision,
            current_fingerprint,
            operation=operation,
            input_hash=manifest.canonical_request_hmac,
        )

    async def execution_manifest_locked(
        self, connection, manifest, record, fingerprint
    ):
        packet = record.context.packet
        if (
            (
                manifest.scope.conversation,
                manifest.scope.task_id,
                manifest.scope.execution_id,
            )
            != (packet.scope, packet.task_id, packet.execution_id)
            or manifest.packet_id != packet.packet_id
            or manifest.packet_revision is None
            or not set(manifest.safety_dependencies).issubset(
                packet.safety_dependencies
            )
            or not any(
                (grant.node_id, grant.execution_agent_id, grant.purpose)
                == (
                    manifest.scope.subtask_id,
                    manifest.scope.execution_agent_id,
                    manifest.scope.purpose,
                )
                for grant in record.context.execution_grants
            )
        ):
            return False
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT o.status,o.input_hash,o.latest_attempt,o.deadline,m.metadata_json FROM agent_context_operation o JOIN agent_context_manifest m USING(tenant_id,task_id,execution_id,operation_id) WHERE o.tenant_id=:tenant AND o.execution_id=:execution AND o.task_id=:task AND o.operation_id=:operation AND m.attempt=:attempt FOR UPDATE"
                    ),
                    self.key(packet.scope, packet.execution_id)
                    | {
                        "task": packet.task_id.encode(),
                        "operation": manifest.operation_id.encode(),
                        "attempt": manifest.attempt,
                    },
                )
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or row["status"] not in {"SENT", "SUCCEEDED", "UNKNOWN"}
            or row["input_hash"] != manifest.canonical_request_hmac
            or row["latest_attempt"] != manifest.attempt
            or not memory_operation_deadline_matches(
                manifest.node_id, row["deadline"], record.deadline_epoch_seconds
            )
            or ContextManifestModel.model_validate_json(row["metadata_json"]).to_core()
            != manifest
        ):
            return False
        return await self._revision_chain_locked(
            connection, record, manifest.packet_revision, fingerprint
        )

    async def validate_manifest_authorization(
        self, manifest, operation, packet, *, packet_digest, semantic_digest
    ):
        async with self.execution_store.engine.begin() as connection:
            owner, record = await self.lock_owner(
                connection, manifest.scope.conversation, manifest.scope.execution_id
            )
            if (
                record.context.packet != packet
                or record.context.packet_digest != packet_digest
                or record.context.semantic_snapshot_digest != semantic_digest
            ):
                return False
            return await self.manifest_authorized_locked(
                connection,
                manifest,
                operation,
                record,
                owner["current_context_fingerprint"],
            )
