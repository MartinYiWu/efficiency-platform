"""原Java execution唯一绑定、加密快照和单调失效回执；不拥有业务Job。"""

import hashlib
import json
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionContext,
    MemoryExecutionRecord,
    MemoryInvalidation,
)

from .memory_cipher import MemorySnapshotCipher, SealedMemorySnapshot

_KEY = "tenant_id=:tenant AND execution_id=:execution"


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


class MySqlMemoryExecutionStore:
    def __init__(self, engine: AsyncEngine, cipher: MemorySnapshotCipher):
        self.engine = engine
        self.cipher = cipher

    def _decode(self, row: Any) -> MemoryExecutionRecord:
        if row["state"] == "SCRUBBED":
            raise ValueError("MEMORY_ACCESS_REVOKED")
        tenant, execution, runtime = (
            bytes(row[key]).decode("utf-8")
            for key in ("tenant_id", "execution_id", "runtime_id")
        )
        raw = self.cipher.open(
            tenant,
            execution,
            runtime,
            SealedMemorySnapshot(
                bytes(row["snapshot_ciphertext"]),
                bytes(row["snapshot_nonce"]),
                row["key_version"],
            ),
        )
        context = MemoryExecutionContext.from_metadata(json.loads(raw))
        if (
            context.packet.scope.tenant_id != tenant
            or context.packet.execution_id != execution
            or _fingerprint(context.metadata()) != row.get("current_context_fingerprint", row["context_fingerprint"])
        ):
            raise ValueError("MEMORY_SNAPSHOT_UNAVAILABLE")
        return MemoryExecutionRecord(
            context,
            runtime,
            row["runtime_kind"],
            row["request_fingerprint"],
            row["original_deadline"],
            row["state"],
            row["execution_revision"],
            row["grant_epoch"],
            row["source_epoch"],
            row["deletion_epoch"],
        )

    async def get(
        self, tenant_id: str, execution_id: str
    ) -> MemoryExecutionRecord | None:
        try:
            async with self.engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text("SELECT * FROM agent_memory_execution WHERE " + _KEY),
                            {
                                "tenant": tenant_id.encode(),
                                "execution": execution_id.encode(),
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
            return None if row is None else self._decode(row)
        except SQLAlchemyError:
            raise ValueError("MEMORY_AUTHORITY_UNAVAILABLE") from None

    async def claim(
        self,
        context: MemoryExecutionContext,
        runtime_id: str,
        runtime_kind: str,
        request_fingerprint: str,
        budget_deadline: int,
    ) -> tuple[MemoryExecutionRecord, bool]:
        if runtime_kind not in {"OPERATIONS", "CUSTOMER_SERVICE", "HR"}:
            raise ValueError("MEMORY_RUNTIME_KIND_INVALID")
        deadline = min(context.deadline_epoch_seconds, budget_deadline)
        if deadline <= 0 or len(request_fingerprint) != 64:
            raise ValueError("MEMORY_EXECUTION_INVALID")
        packet = context.packet
        tenant, execution = packet.scope.tenant_id, packet.execution_id
        sealed = self.cipher.seal(
            tenant,
            execution,
            runtime_id,
            json.dumps(
                context.metadata(), ensure_ascii=False, separators=(",", ":")
            ).encode(),
        )
        params = {
            "tenant": tenant.encode(),
            "execution": execution.encode(),
            "runtime": runtime_id.encode(),
            "kind": runtime_kind,
            "fingerprint": request_fingerprint,
            "context_fingerprint": _fingerprint(context.metadata()),
            "ciphertext": sealed.ciphertext,
            "nonce": sealed.nonce,
            "key_version": sealed.key_version,
            "deadline": deadline,
            "revision": packet.execution_revision,
            "grant": packet.grant_epoch,
            "source": packet.source_epoch,
            "deletion": packet.deletion_epoch,
        }
        try:
            async with self.engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO agent_memory_execution (tenant_id,execution_id,runtime_id,runtime_kind,request_fingerprint,"
                        "context_fingerprint,current_context_fingerprint,snapshot_ciphertext,snapshot_nonce,key_version,original_deadline,execution_revision,"
                        "grant_epoch,source_epoch,deletion_epoch,state) VALUES (:tenant,:execution,:runtime,:kind,:fingerprint,"
                        ":context_fingerprint,:context_fingerprint,:ciphertext,:nonce,:key_version,:deadline,:revision,:grant,:source,:deletion,'ACTIVE')"
                    ),
                    params,
                )
            return MemoryExecutionRecord(
                context,
                runtime_id,
                runtime_kind,
                request_fingerprint,
                deadline,
                "ACTIVE",
                packet.execution_revision,
                packet.grant_epoch,
                packet.source_epoch,
                packet.deletion_epoch,
            ), True
        except IntegrityError:
            original = await self.get(tenant, execution)
            if (
                original is None
                or original.context != context
                or original.runtime_kind != runtime_kind
                or original.request_fingerprint != request_fingerprint
            ):
                raise ValueError("MEMORY_EXECUTION_CONFLICT_409") from None
            if original.state != "ACTIVE":
                raise ValueError("MEMORY_ACCESS_REVOKED") from None
            return original, False
        except SQLAlchemyError:
            raise ValueError("MEMORY_AUTHORITY_UNAVAILABLE") from None

    async def invalidate(self, event: MemoryInvalidation) -> str:
        params = {
            "tenant": event.tenant_id.encode(),
            "execution": event.execution_id.encode(),
            "event": event.event_id.encode(),
            "fingerprint": _fingerprint(asdict(event)),
            "revision": event.expected_execution_revision,
            "grant": event.grant_epoch,
            "source": event.source_epoch,
            "deletion": event.deletion_epoch,
        }
        try:
            async with self.engine.begin() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM agent_memory_execution WHERE "
                                + _KEY
                                + " FOR UPDATE"
                            ),
                            params,
                        )
                    )
                    .mappings()
                    .first()
                )
                if row is None:
                    raise ValueError("MEMORY_EXECUTION_NOT_FOUND")
                prior = (
                    (
                        await connection.execute(
                            text(
                                "SELECT event_fingerprint,receipt_ref FROM agent_memory_invalidation_receipt WHERE tenant_id=:tenant AND event_id=:event"
                            ),
                            params,
                        )
                    )
                    .mappings()
                    .first()
                )
                if prior is not None:
                    if prior["event_fingerprint"] != params["fingerprint"]:
                        raise ValueError("MEMORY_INVALIDATION_CONFLICT_409")
                    return str(prior["receipt_ref"])
                if (
                    row["execution_revision"] != event.expected_execution_revision
                    or event.grant_epoch < row["grant_epoch"]
                    or event.source_epoch < row["source_epoch"]
                    or event.deletion_epoch < row["deletion_epoch"]
                ):
                    raise ValueError("MEMORY_INVALIDATION_CONFLICT_409")
                await connection.execute(
                    text(
                        "UPDATE agent_memory_execution SET state=IF(state='SCRUBBED','SCRUBBED','REVOKED'),grant_epoch=:grant,source_epoch=:source,"
                        "deletion_epoch=:deletion WHERE " + _KEY
                    ),
                    params,
                )
                receipt = "memory-stop-" + uuid4().hex
                await connection.execute(
                    text(
                        "INSERT INTO agent_memory_invalidation_receipt(tenant_id,event_id,execution_id,event_fingerprint,receipt_ref) "
                        "VALUES(:tenant,:event,:execution,:fingerprint,:receipt)"
                    ),
                    params | {"receipt": receipt},
                )
                return receipt
        except SQLAlchemyError:
            raise ValueError("MEMORY_AUTHORITY_UNAVAILABLE") from None
