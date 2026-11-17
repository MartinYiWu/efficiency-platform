"""单库刷新journal适配器；原财务与请求锚永久保留。"""

import hashlib
import json
from dataclasses import asdict

from sqlalchemy import text

from efficiency_platform_agent.core.memory import ConversationScope
from efficiency_platform_agent.core.memory_refresh import (
    CheckpointMode,
    MemoryContextWait,
    WaitPhase,
)

from .memory_cipher import SealedMemorySnapshot
from .memory_execution import _fingerprint

_KEY = "tenant_id=:tenant AND execution_id=:execution"


class MySqlMemoryContextRefreshStore:
    def __init__(self, execution_store):
        self.execution_store = execution_store

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

    def wait(self, row, refresh_count):
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
            CheckpointMode(row["checkpoint_mode"]),
            decode("checkpoint_ns"),
            decode("checkpoint_id"),
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
        await connection.execute(
            text(
                "UPDATE agent_memory_context_refresh SET phase='SNAPSHOT_APPLIED' WHERE "
                + _KEY
                + " AND record_kind='REFRESH' AND record_id=:record AND phase='PENDING'"
            ),
            self.key(wait.scope, wait.execution_id)
            | {"record": bytes(candidate["record_id"])},
        )
