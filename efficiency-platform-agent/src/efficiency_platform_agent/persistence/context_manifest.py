"""MySQL Manifest、原操作回执与受信发送结果的原子持久化。"""

import hashlib
import json
from dataclasses import asdict

from pydantic import TypeAdapter
from sqlalchemy import LargeBinary, bindparam, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import TextClause

from efficiency_platform_agent.contracts.context_control import ContextManifestModel
from efficiency_platform_agent.core.context_control import ContextManifest
from efficiency_platform_agent.core.context_ports import (
    ContextOperation,
    OperationReceipt,
)
from efficiency_platform_agent.core.memory import ExecutionScope
from efficiency_platform_agent.core.memory_execution import (
    MemorySendPermit,
    MemorySendPermitAuthority,
    memory_operation_deadline_matches,
)
from efficiency_platform_agent.core.run import ProviderResult

from .memory_context_refresh import MySqlMemoryContextRefreshStore, _journal_binding
from .memory_execution import _fingerprint

_RESULT = TypeAdapter(ProviderResult)

_KEY = "tenant_id=:tenant_id AND task_id=:task_id AND execution_id=:execution_id AND operation_id=:operation_id"


def _key(scope: ExecutionScope, operation_id: str) -> dict[str, object]:
    return {
        "tenant_id": scope.conversation.tenant_id.encode("utf-8"),
        "task_id": scope.task_id.encode("utf-8"),
        "execution_id": scope.execution_id.encode("utf-8"),
        "operation_id": operation_id.encode("utf-8"),
    }


def _statement(sql: str) -> TextClause:
    return text(sql).bindparams(
        *(
            bindparam(name, type_=LargeBinary(512))
            for name in ("tenant_id", "task_id", "execution_id", "operation_id")
        )
    )


class MySqlContextManifestStore:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        memory_execution_store=None,
        result_fault_hook=None,
    ):
        self._engine = engine
        if (
            memory_execution_store is not None
            and memory_execution_store.engine is not engine
        ):
            raise ValueError("MEMORY_RESULT_ENGINE_MISMATCH")
        self._memory_execution_store = memory_execution_store
        self._result_authority: MemorySendPermitAuthority | None = None
        self._result_fault_hook = result_fault_hook

    def install_result_authority(self, authority: MemorySendPermitAuthority) -> None:
        if self._result_authority is not None or not callable(
            getattr(authority, "validate", None)
        ):
            raise ValueError("MEMORY_RESULT_AUTHORITY_ALREADY_CONFIGURED")
        self._result_authority = authority

    async def _validate_permit(self, manifest, operation, permit):
        if (
            not isinstance(permit, MemorySendPermit)
            or self._result_authority is None
            or self._memory_execution_store is None
            or not await self._result_authority.validate(permit)
        ):
            raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        if (
            permit.scope != manifest.scope
            or permit.operation_id != manifest.operation_id
            or permit.operation_id != operation.operation_id
            or permit.attempt != manifest.attempt
            or permit.attempt != operation.attempt
            or permit.input_hash != manifest.canonical_request_hmac
            or permit.manifest_id != manifest.manifest_id
            or permit.packet_id != manifest.packet_id
            or permit.deadline_epoch_seconds != operation.deadline_epoch_seconds
            or operation.memory_disabled
        ):
            raise PermissionError("MEMORY_RESULT_BINDING_MISMATCH")

    async def _lock_result_owner(self, conn, manifest, operation, permit):
        journal = MySqlMemoryContextRefreshStore(self._memory_execution_store)
        owner, record = await journal.lock_owner(
            conn, manifest.scope.conversation, manifest.scope.execution_id
        )
        packet = record.context.packet
        if (
            record.runtime_id != permit.runtime_id
            or record.execution_revision != permit.execution_revision
            or not memory_operation_deadline_matches(
                manifest.node_id,
                permit.deadline_epoch_seconds,
                record.deadline_epoch_seconds,
            )
            or (packet.scope, packet.task_id, packet.execution_id)
            != (
                manifest.scope.conversation,
                manifest.scope.task_id,
                manifest.scope.execution_id,
            )
            or packet.packet_id != permit.packet_id
            or packet.packet_revision != permit.packet_revision
            or record.context.packet_digest != permit.packet_digest
            or not set(manifest.safety_dependencies).issubset(
                packet.safety_dependencies
            )
            or (record.grant_epoch, record.source_epoch, record.deletion_epoch)
            != (packet.grant_epoch, packet.source_epoch, packet.deletion_epoch)
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
            raise PermissionError("MEMORY_RESULT_BINDING_MISMATCH")
        params = _key(manifest.scope, manifest.operation_id) | {
            "attempt": manifest.attempt
        }
        row = (
            (
                await conn.execute(
                    _statement(
                        "SELECT * FROM agent_context_operation WHERE "
                        + _KEY
                        + " FOR UPDATE"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        saved = (
            await conn.execute(
                _statement(
                    "SELECT metadata_json FROM agent_context_manifest WHERE "
                    + _KEY
                    + " AND attempt=:attempt FOR UPDATE"
                ),
                params,
            )
        ).scalar_one_or_none()
        if (
            row is None
            or row["input_hash"] != permit.input_hash
            or row["deadline"] != operation.deadline_epoch_seconds
            or row["latest_attempt"] != permit.attempt
            or saved is None
            or ContextManifestModel.model_validate_json(saved).to_core() != manifest
        ):
            raise PermissionError("MEMORY_RESULT_BINDING_MISMATCH")
        if not await journal.manifest_authorized_locked(
            conn, manifest, operation, record, owner["current_context_fingerprint"]
        ):
            raise PermissionError("MEMORY_RESULT_BINDING_MISMATCH")
        return journal, owner, record, row

    @staticmethod
    def _result_id(operation_id, attempt):
        operation = operation_id.encode()
        return hashlib.sha256(
            str(len(operation)).encode()
            + b":"
            + operation
            + b":"
            + str(attempt).encode()
        ).hexdigest()

    async def _result_fault(self, point):
        if self._result_fault_hook is not None:
            await self._result_fault_hook(point)

    async def capture_result_once(self, manifest, operation, send_permit, result):
        await self._validate_permit(manifest, operation, send_permit)
        if not isinstance(result, ProviderResult) or result.error is not None:
            raise ValueError("MEMORY_RESULT_INCOMPLETE")
        body = {
            "schema_version": "memory-provider-result/1",
            "permit": asdict(send_permit),
            "manifest": json.loads(
                ContextManifestModel.from_core(manifest).model_dump_json()
            ),
            "result": json.loads(_RESULT.dump_json(result)),
        }
        result_hash = _fingerprint(body["result"])
        record_id = self._result_id(manifest.operation_id, manifest.attempt)
        ref = "memory-result:" + record_id
        try:
            async with self._engine.begin() as conn:
                journal, owner, record, operation_row = await self._lock_result_owner(
                    conn, manifest, operation, send_permit
                )
                existing = await journal.record(
                    conn,
                    manifest.scope.conversation,
                    manifest.scope.execution_id,
                    "RESULT",
                    record_id,
                )
                if existing is not None:
                    saved = journal.body(existing)
                    if (
                        existing["result_hash"] != result_hash
                        or saved != body
                        or existing["request_hash"] != _fingerprint(body)
                    ):
                        raise ValueError("MEMORY_RESULT_CONFLICT")
                    if (
                        operation_row["status"] != "SUCCEEDED"
                        or operation_row["receipt_ref"] != ref
                    ):
                        raise ValueError("MEMORY_RESULT_UNAVAILABLE")
                    return ref
                if operation_row["status"] not in {"SENT", "UNKNOWN"}:
                    raise ValueError("MEMORY_RESULT_UNAVAILABLE")
                scope = manifest.scope.conversation
                data = {
                    "tenant_id": scope.tenant_id.encode(),
                    "execution_id": manifest.scope.execution_id.encode(),
                    "record_kind": "RESULT",
                    "record_id": record_id.encode(),
                    "runtime_id": send_permit.runtime_id.encode(),
                    "task_id": manifest.scope.task_id.encode(),
                    "user_id": scope.user_id.encode(),
                    "domain": scope.domain,
                    "top_level_agent_id": scope.top_level_agent_id,
                    "session_kind": scope.session_kind,
                    "session_id": None
                    if scope.session_id is None
                    else scope.session_id.encode(),
                    "request_hash": _fingerprint(body),
                    "request_fingerprint": record.request_fingerprint,
                    "semantic_input_hash": record.context.packet.semantic_input_hash,
                    "operation_id": manifest.operation_id.encode(),
                    "attempt": manifest.attempt,
                    "canonical_request_hmac": manifest.canonical_request_hmac,
                    "execution_revision": record.execution_revision,
                    "original_deadline": record.deadline_epoch_seconds,
                    "old_packet_revision": record.context.packet.packet_revision,
                    "expected_current_context_fingerprint": owner[
                        "current_context_fingerprint"
                    ],
                    "phase": "CAPTURED",
                    "sent_packet_revision": send_permit.packet_revision,
                    "sent_packet_digest": send_permit.packet_digest,
                    "send_permit_hash": _fingerprint(asdict(send_permit)),
                    "result_hash": result_hash,
                }
                sealed = self._memory_execution_store.cipher.seal_journal(
                    tuple(asdict(scope).values()),
                    manifest.scope.execution_id,
                    send_permit.runtime_id,
                    record_id,
                    "RESULT",
                    json.dumps(
                        body, ensure_ascii=False, separators=(",", ":")
                    ).encode(),
                    binding=_journal_binding(data),
                    key_version=record.key_version,
                )
                data.update(
                    body_ciphertext=sealed.ciphertext,
                    body_nonce=sealed.nonce,
                    key_version=sealed.key_version,
                )
                await conn.execute(
                    text(
                        "INSERT INTO agent_memory_context_refresh ("
                        + ",".join(data)
                        + ") VALUES ("
                        + ",".join(":" + key for key in data)
                        + ")"
                    ),
                    data,
                )
                await self._result_fault("after_result_insert")
                changed = await conn.execute(
                    _statement(
                        "UPDATE agent_context_operation SET status='SUCCEEDED',receipt_ref=:ref WHERE "
                        + _KEY
                        + " AND status IN ('SENT','UNKNOWN') AND input_hash=:hmac AND latest_attempt=:attempt AND deadline=:deadline"
                    ),
                    _key(manifest.scope, manifest.operation_id)
                    | {
                        "ref": ref,
                        "hmac": send_permit.input_hash,
                        "attempt": send_permit.attempt,
                        "deadline": send_permit.deadline_epoch_seconds,
                    },
                )
                if changed.rowcount != 1:
                    raise ValueError("MEMORY_RESULT_UNAVAILABLE")
                await self._result_fault("after_result_receipt")
            await self._result_fault("after_result_commit")
            return ref
        except SQLAlchemyError as exc:
            code = getattr(exc.orig, "args", (None,))[0]
            raise ValueError(
                "MEMORY_REFRESH_SCHEMA_REQUIRED"
                if code in {1054, 1146}
                else "MEMORY_AUTHORITY_UNAVAILABLE"
            ) from None

    async def get_captured_result(self, manifest, operation, send_permit):
        await self._validate_permit(manifest, operation, send_permit)
        record_id = self._result_id(manifest.operation_id, manifest.attempt)
        try:
            async with self._engine.begin() as conn:
                journal, _, _, row = await self._lock_result_owner(
                    conn, manifest, operation, send_permit
                )
                saved = await journal.record(
                    conn,
                    manifest.scope.conversation,
                    manifest.scope.execution_id,
                    "RESULT",
                    record_id,
                )
                if (
                    saved is None
                    or row["status"] != "SUCCEEDED"
                    or row["receipt_ref"] != "memory-result:" + record_id
                ):
                    raise ValueError("MEMORY_RESULT_UNAVAILABLE")
                body = journal.body(saved)
                if (
                    body.get("schema_version") != "memory-provider-result/1"
                    or body.get("permit") != json.loads(json.dumps(asdict(send_permit)))
                    or body.get("manifest")
                    != json.loads(
                        ContextManifestModel.from_core(manifest).model_dump_json()
                    )
                    or saved["request_hash"] != _fingerprint(body)
                    or saved["result_hash"] != _fingerprint(body["result"])
                ):
                    raise ValueError("MEMORY_RESULT_UNAVAILABLE")
                return _RESULT.validate_python(body["result"])
        except SQLAlchemyError as exc:
            code = getattr(exc.orig, "args", (None,))[0]
            raise ValueError(
                "MEMORY_REFRESH_SCHEMA_REQUIRED"
                if code in {1054, 1146}
                else "MEMORY_AUTHORITY_UNAVAILABLE"
            ) from None

    async def execution_manifests(
        self, tenant_id: str, execution_id: str
    ) -> tuple[ContextManifest, ...]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT m.metadata_json FROM agent_context_manifest m JOIN agent_context_operation o "
                            "ON o.tenant_id=m.tenant_id AND o.task_id=m.task_id AND o.execution_id=m.execution_id AND o.operation_id=m.operation_id "
                            "WHERE m.tenant_id=:tenant AND m.execution_id=:execution AND o.status IN ('SENT','SUCCEEDED','UNKNOWN') "
                            "ORDER BY m.operation_id,m.attempt"
                        ),
                        {
                            "tenant": tenant_id.encode(),
                            "execution": execution_id.encode(),
                        },
                    )
                )
                .scalars()
                .all()
            )
        return tuple(
            ContextManifestModel.model_validate_json(value).to_core() for value in rows
        )

    async def save_manifest_once(
        self, manifest: ContextManifest, operation: ContextOperation
    ) -> ContextManifest:
        if (manifest.operation_id, manifest.attempt) != (
            operation.operation_id,
            operation.attempt,
        ):
            raise ValueError("CONTEXT_OPERATION_MISMATCH")
        params = _key(manifest.scope, manifest.operation_id) | {
            "attempt": manifest.attempt,
            "input_hash": manifest.canonical_request_hmac,
            "deadline": operation.deadline_epoch_seconds,
            "metadata": ContextManifestModel.from_core(manifest).model_dump_json(),
        }
        for retry in range(2):
            try:
                async with self._engine.begin() as conn:
                    row = (
                        (
                            await conn.execute(
                                _statement(
                                    "SELECT input_hash,status,deadline,latest_attempt FROM agent_context_operation WHERE "
                                    + _KEY
                                ),
                                params,
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if row is None:
                        if operation.attempt != 1:
                            raise ValueError("CONTEXT_ATTEMPT_INVALID")
                        await conn.execute(
                            _statement(
                                "INSERT INTO agent_context_operation (tenant_id,task_id,execution_id,operation_id,input_hash,status,deadline,latest_attempt) VALUES (:tenant_id,:task_id,:execution_id,:operation_id,:input_hash,'NOT_SENT',:deadline,:attempt)"
                            ),
                            params,
                        )
                    elif (
                        row["input_hash"] != params["input_hash"]
                        or row["deadline"] != params["deadline"]
                    ):
                        raise ValueError("CONTEXT_MANIFEST_CONFLICT_409")
                    existing = (
                        await conn.execute(
                            _statement(
                                "SELECT metadata_json FROM agent_context_manifest WHERE "
                                + _KEY
                                + " AND attempt=:attempt"
                            ),
                            params,
                        )
                    ).scalar_one_or_none()
                    if existing is not None:
                        return ContextManifestModel.model_validate_json(
                            existing
                        ).to_core()
                    if row is not None and operation.attempt != row["latest_attempt"]:
                        if (
                            row["status"] != "NOT_SENT"
                            or operation.attempt != row["latest_attempt"] + 1
                        ):
                            raise ValueError("CONTEXT_ATTEMPT_INVALID")
                        changed = await conn.execute(
                            _statement(
                                "UPDATE agent_context_operation SET latest_attempt=:attempt WHERE "
                                + _KEY
                                + " AND status='NOT_SENT' AND latest_attempt=:previous_attempt"
                            ),
                            params | {"previous_attempt": row["latest_attempt"]},
                        )
                        if changed.rowcount != 1:
                            raise ValueError("CONTEXT_OPERATION_BLOCKED")
                    if row is not None and row["status"] != "NOT_SENT":
                        raise ValueError("CONTEXT_OPERATION_BLOCKED")
                    await conn.execute(
                        _statement(
                            "INSERT INTO agent_context_manifest (tenant_id,task_id,execution_id,operation_id,attempt,input_hash,metadata_json) VALUES (:tenant_id,:task_id,:execution_id,:operation_id,:attempt,:input_hash,:metadata)"
                        ),
                        params,
                    )
                    return manifest
            except IntegrityError:
                if retry:
                    raise ValueError("CONTEXT_MANIFEST_CONFLICT_409") from None
        raise RuntimeError("CONTEXT_MANIFEST_UNAVAILABLE")

    async def get_operation_receipt(
        self, scope: ExecutionScope, operation_id: str
    ) -> OperationReceipt | None:
        async with self._engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        _statement(
                            "SELECT input_hash,status,deadline,receipt_ref,latest_attempt FROM agent_context_operation WHERE "
                            + _KEY
                        ),
                        _key(scope, operation_id),
                    )
                )
                .mappings()
                .first()
            )
            return (
                None
                if row is None
                else OperationReceipt(
                    row["input_hash"],
                    row["status"],
                    row["deadline"],
                    row["receipt_ref"],
                    row["latest_attempt"],
                )
            )

    async def mark_sending(
        self, manifest: ContextManifest, operation: ContextOperation
    ) -> bool:
        params = _key(manifest.scope, manifest.operation_id) | {
            "input_hash": manifest.canonical_request_hmac,
            "deadline": operation.deadline_epoch_seconds,
            "attempt": manifest.attempt,
        }
        async with self._engine.begin() as conn:
            result = await conn.execute(
                _statement(
                    "UPDATE agent_context_operation SET status='SENT' WHERE "
                    + _KEY
                    + " AND input_hash=:input_hash AND deadline=:deadline AND latest_attempt=:attempt AND status='NOT_SENT' AND EXISTS (SELECT 1 FROM agent_context_manifest m WHERE m.tenant_id=:tenant_id AND m.task_id=:task_id AND m.execution_id=:execution_id AND m.operation_id=:operation_id AND m.attempt=:attempt AND m.input_hash=:input_hash)"
                ),
                params,
            )
            return result.rowcount == 1

    async def record_receipt(
        self, manifest: ContextManifest, status: str, receipt_ref: str | None = None
    ) -> bool:
        if status not in {"SUCCEEDED", "UNKNOWN"}:
            raise ValueError("CONTEXT_RECEIPT_INVALID")
        OperationReceipt(manifest.canonical_request_hmac, status, 0, receipt_ref)
        params = _key(manifest.scope, manifest.operation_id) | {
            "input_hash": manifest.canonical_request_hmac,
            "status": status,
            "receipt_ref": receipt_ref,
            "attempt": manifest.attempt,
        }
        async with self._engine.begin() as conn:
            result = await conn.execute(
                _statement(
                    "UPDATE agent_context_operation SET status=:status,receipt_ref=:receipt_ref WHERE "
                    + _KEY
                    + " AND input_hash=:input_hash AND latest_attempt=:attempt AND (status='SENT' OR (status='UNKNOWN' AND :status='SUCCEEDED'))"
                ),
                params,
            )
            return result.rowcount == 1
