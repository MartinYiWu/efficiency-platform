"""仅保存元数据的 MySQL Manifest 与操作回执适配器。"""

from sqlalchemy import LargeBinary, bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import TextClause

from efficiency_platform_agent.contracts.context_control import ContextManifestModel
from efficiency_platform_agent.core.context_control import ContextManifest
from efficiency_platform_agent.core.context_ports import (
    ContextOperation,
    OperationReceipt,
)
from efficiency_platform_agent.core.memory import ExecutionScope

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
    def __init__(self, engine: AsyncEngine):
        self._engine = engine

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
