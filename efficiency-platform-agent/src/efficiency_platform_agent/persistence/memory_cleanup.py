"""真实停止及thread清理后，原子擦除技术快照并保留财务/身份锚点。"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from efficiency_platform_agent.core.memory import ConversationScope, SourceDependency
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionRecord,
    MemoryInvalidation,
)

from .memory_execution import _fingerprint


class MySqlMemoryCleanupJournal:
    def __init__(self, engine: AsyncEngine, *, refresh_schema_required: bool = False):
        self.engine = engine
        self.refresh_schema_required = refresh_schema_required
        self.runtime_scrubber: (
            Callable[[MemoryExecutionRecord], Awaitable[bool]] | None
        ) = None

    async def _verify_refresh_erasure(self, connection, params):
        if not self.refresh_schema_required:
            return
        remaining = (await connection.execute(
            text("SELECT COUNT(*) FROM agent_memory_context_refresh WHERE tenant_id=:tenant AND execution_id=:execution AND (body_ciphertext IS NOT NULL OR body_nonce IS NOT NULL OR body_scrub_event_id IS NULL)"),params,
        )).scalar_one()
        if remaining:
            raise ValueError("MEMORY_CLEANUP_PROOF_REQUIRED")

    @staticmethod
    def _parameters(
        event: MemoryInvalidation, dependencies: tuple[SourceDependency, ...]
    ):
        normalized = sorted(
            (asdict(dep) for dep in set(dependencies)),
            key=lambda value: json.dumps(value, sort_keys=True),
        )
        return {
            "tenant": event.tenant_id.encode(),
            "execution": event.execution_id.encode(),
            "event": event.event_id.encode(),
            "fingerprint": _fingerprint(asdict(event)),
            "revision": event.expected_execution_revision,
            "grant": event.grant_epoch,
            "source": event.source_epoch,
            "deletion": event.deletion_epoch,
            "cleanup": _fingerprint(
                {"event": asdict(event), "dependencies": normalized}
            ),
        }

    @staticmethod
    def _check(row, params):
        if (
            row is None
            or bytes(row["execution_id"]) != params["execution"]
            or row["event_fingerprint"] != params["fingerprint"]
        ):
            raise ValueError("MEMORY_CLEANUP_CONFLICT_409")
        if row["cleanup_fingerprint"] not in (None, params["cleanup"]):
            raise ValueError("MEMORY_CLEANUP_CONFLICT_409")

    async def revoke(self, event: MemoryInvalidation, dependencies: tuple[SourceDependency, ...], record: MemoryExecutionRecord) -> str:
        packet = record.context.packet
        original = (packet.grant_epoch, packet.source_epoch, packet.deletion_epoch)
        requested = (event.grant_epoch, event.source_epoch, event.deletion_epoch)
        if (packet.scope.tenant_id != event.tenant_id or packet.execution_id != event.execution_id
            or packet.execution_revision != event.expected_execution_revision or not dependencies
            or not set(dependencies).issubset(packet.safety_dependencies)
            or any(new < old for new, old in zip(requested, original, strict=True)) or requested == original):
            raise ValueError("MEMORY_CLEANUP_CONFLICT_409")
        params = self._parameters(event, dependencies)
        try:
            async with self.engine.begin() as connection:
                execution = (await connection.execute(text("SELECT state,execution_revision,grant_epoch,source_epoch,deletion_epoch FROM agent_memory_execution WHERE tenant_id=:tenant AND execution_id=:execution FOR UPDATE"), params)).mappings().first()
                if execution is None or execution["state"] not in {"ACTIVE", "REVOKED"} or execution["execution_revision"] != event.expected_execution_revision:
                    raise ValueError("MEMORY_CLEANUP_CONFLICT_409")
                prior = (await connection.execute(text("SELECT * FROM agent_memory_invalidation_receipt WHERE tenant_id=:tenant AND event_id=:event FOR UPDATE"), params)).mappings().first()
                if prior is not None:
                    self._check(prior, params)
                    if prior["expected_execution_revision"] is None:
                        raise ValueError("MEMORY_CLEANUP_MAPPING_REQUIRED")
                    return prior["receipt_ref"]
                effective = params | {"grant": max(event.grant_epoch, execution["grant_epoch"]),
                    "source": max(event.source_epoch, execution["source_epoch"]), "deletion": max(event.deletion_epoch, execution["deletion_epoch"])}
                receipt = "memory-stop-" + uuid4().hex
                await connection.execute(text("UPDATE agent_memory_execution SET state='REVOKED',grant_epoch=:grant,source_epoch=:source,deletion_epoch=:deletion WHERE tenant_id=:tenant AND execution_id=:execution"), effective)
                await connection.execute(text("INSERT INTO agent_memory_invalidation_receipt(tenant_id,event_id,execution_id,event_fingerprint,receipt_ref,cleanup_fingerprint,expected_execution_revision,grant_epoch,source_epoch,deletion_epoch) VALUES(:tenant,:event,:execution,:fingerprint,:receipt,:cleanup,:revision,:grant,:source,:deletion)"), effective | {"receipt": receipt})
                return receipt
        except SQLAlchemyError:
            raise ValueError("MEMORY_CLEANUP_STORE_UNAVAILABLE") from None

    async def receipts(
        self, event: MemoryInvalidation, dependencies: tuple[SourceDependency, ...]
    ) -> dict[str, str]:
        params = self._parameters(event, dependencies)
        try:
            async with self.engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM agent_memory_invalidation_receipt WHERE tenant_id=:tenant AND event_id=:event"
                            ),
                            params,
                        )
                    )
                    .mappings()
                    .first()
                )
            if row is None:
                return await self._scrubbed_receipts(event, dependencies)
            self._check(row, params)
            result = {}
            if row["stop_confirmed"]:
                result["AGENT_STOP"] = row["receipt_ref"]
            for key, column in (
                ("THREADS", "threads_receipt"),
                ("SNAPSHOT", "scrub_receipt"),
            ):
                if row[column] is not None:
                    result[key] = row[column]
            verified = await self._scrubbed_receipts(event, dependencies)
            if "SNAPSHOT" in result and not verified:
                raise ValueError("MEMORY_CLEANUP_PROOF_REQUIRED")
            return verified or result
        except SQLAlchemyError:
            raise ValueError("MEMORY_CLEANUP_STORE_UNAVAILABLE") from None

    async def _scrubbed_receipts(
        self, event: MemoryInvalidation, dependencies: tuple[SourceDependency, ...]
    ) -> dict[str, str]:
        params = self._parameters(event, dependencies)
        async with self.engine.begin() as connection:
            execution = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM agent_memory_execution WHERE tenant_id=:tenant AND execution_id=:execution FOR UPDATE"
                        ),
                        params,
                    )
                )
                .mappings()
                .first()
            )
            if execution is None or execution["state"] != "SCRUBBED":
                return {}
            await self._verify_refresh_erasure(connection,params)
            raw = execution["scrub_authority"]
            authority = json.loads(raw) if isinstance(raw, str) else raw
            if (
                not isinstance(authority, dict)
                or set(authority)
                != {
                    "schema_version",
                    "scope",
                    "task_id",
                    "execution_id",
                    "execution_revision",
                    "safety_dependencies",
                "original_epochs",
                }
                or authority["schema_version"] != "memory-scrub-authority/1"
            ):
                raise ValueError("MEMORY_CLEANUP_PROOF_REQUIRED")
            scope = ConversationScope(**authority["scope"])
            original = tuple(
                SourceDependency(**dep) for dep in authority["safety_dependencies"]
            )
            original_epochs = authority["original_epochs"]
            if not isinstance(original_epochs, list) or len(original_epochs) != 3 or any(type(value) is not int or value < 0 for value in original_epochs):
                raise ValueError("MEMORY_CLEANUP_PROOF_REQUIRED")
            requested_epochs = (event.grant_epoch, event.source_epoch, event.deletion_epoch)
            if (
                scope.tenant_id != event.tenant_id
                or authority["execution_id"] != event.execution_id
                or authority["execution_revision"] != event.expected_execution_revision
                or execution["execution_revision"] != event.expected_execution_revision
                or not dependencies
                or not set(dependencies).issubset(original)
                or any(new < old for new, old in zip(requested_epochs, original_epochs, strict=True))
                or requested_epochs == tuple(original_epochs)
                or execution["snapshot_ciphertext"] is not None
                or execution["snapshot_nonce"] is not None
            ):
                raise ValueError("MEMORY_CLEANUP_CONFLICT_409")
            proof = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM agent_memory_invalidation_receipt WHERE tenant_id=:tenant AND event_id=:original FOR UPDATE"
                        ),
                        params | {"original": execution["scrub_event_id"]},
                    )
                )
                .mappings()
                .first()
            )
            if (
                proof is None
                or bytes(proof["execution_id"]) != params["execution"]
                or not proof["stop_confirmed"]
                or proof["threads_receipt"] is None
                or proof["scrub_receipt"] is None
                or proof["cleanup_fingerprint"] is None
            ):
                raise ValueError("MEMORY_CLEANUP_PROOF_REQUIRED")
            stop_receipt = str(proof["receipt_ref"])
            existing = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM agent_memory_invalidation_receipt WHERE tenant_id=:tenant AND event_id=:event FOR UPDATE"
                        ),
                        params,
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                self._check(existing, params)
                if (
                    existing["stop_confirmed"]
                    and existing["threads_receipt"] is not None
                    and existing["scrub_receipt"] is not None
                ):
                    proof = existing
                    stop_receipt = str(existing["receipt_ref"])
                else:
                    await connection.execute(
                        text(
                            "UPDATE agent_memory_invalidation_receipt SET cleanup_fingerprint=:cleanup,stop_confirmed=TRUE,threads_receipt=:threads,scrub_receipt=:scrub WHERE tenant_id=:tenant AND event_id=:event"
                        ),
                        params
                        | {
                            "stop": proof["receipt_ref"],
                            "threads": proof["threads_receipt"],
                            "scrub": proof["scrub_receipt"],
                        },
                    )
                    stop_receipt = str(existing["receipt_ref"])
            else:
                await connection.execute(
                    text(
                        "INSERT INTO agent_memory_invalidation_receipt(tenant_id,event_id,execution_id,event_fingerprint,receipt_ref,cleanup_fingerprint,stop_confirmed,threads_receipt,scrub_receipt,expected_execution_revision,grant_epoch,source_epoch,deletion_epoch) VALUES(:tenant,:event,:execution,:fingerprint,:stop,:cleanup,TRUE,:threads,:scrub,:revision,:grant,:source,:deletion)"
                    ),
                    params | {"grant": max(event.grant_epoch, execution["grant_epoch"]), "source": max(event.source_epoch, execution["source_epoch"]), "deletion": max(event.deletion_epoch, execution["deletion_epoch"])}
                    | {
                        "stop": proof["receipt_ref"],
                        "threads": proof["threads_receipt"],
                        "scrub": proof["scrub_receipt"],
                    },
                )
            await connection.execute(
                text(
                    "UPDATE agent_memory_execution SET grant_epoch=GREATEST(grant_epoch,:grant),source_epoch=GREATEST(source_epoch,:source),deletion_epoch=GREATEST(deletion_epoch,:deletion) WHERE tenant_id=:tenant AND execution_id=:execution"
                ),
                params,
            )
            return {
                "AGENT_STOP": stop_receipt,
                "THREADS": proof["threads_receipt"],
                "SNAPSHOT": proof["scrub_receipt"],
            }

    async def confirm(
        self,
        event: MemoryInvalidation,
        dependencies: tuple[SourceDependency, ...],
        target: str,
        receipt: str,
    ) -> None:
        params = self._parameters(event, dependencies)
        if target not in {"AGENT_STOP", "THREADS"}:
            raise ValueError("MEMORY_CLEANUP_TARGET_INVALID")
        try:
            async with self.engine.begin() as connection:
                execution = (
                    (
                        await connection.execute(
                            text(
                                "SELECT state,execution_revision,grant_epoch,source_epoch,deletion_epoch FROM agent_memory_execution WHERE tenant_id=:tenant AND execution_id=:execution FOR UPDATE"
                            ),
                            params,
                        )
                    )
                    .mappings()
                    .first()
                )
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM agent_memory_invalidation_receipt WHERE tenant_id=:tenant AND event_id=:event FOR UPDATE"
                            ),
                            params,
                        )
                    )
                    .mappings()
                    .first()
                )
                self._check(row, params)
                assert row is not None
                if (
                    execution is None
                    or execution["state"] != "REVOKED"
                    or tuple(
                        execution[key]
                        for key in (
                            "execution_revision",
                            "grant_epoch",
                            "source_epoch",
                            "deletion_epoch",
                        )
                    )
                    != (
                        row["expected_execution_revision"],
                        row["grant_epoch"],
                        row["source_epoch"],
                        row["deletion_epoch"],
                    )
                ):
                    raise ValueError("MEMORY_REVOCATION_NOT_PERSISTED")
                if target == "AGENT_STOP" and row["receipt_ref"] != receipt:
                    raise ValueError("MEMORY_CLEANUP_CONFLICT_409")
                if target == "THREADS" and (
                    not row["stop_confirmed"]
                    or row["threads_receipt"] not in (None, receipt)
                ):
                    raise ValueError("MEMORY_CLEANUP_CONFLICT_409")
                assignment = (
                    "stop_confirmed=TRUE"
                    if target == "AGENT_STOP"
                    else "threads_receipt=:receipt"
                )
                await connection.execute(
                    text(
                        "UPDATE agent_memory_invalidation_receipt SET cleanup_fingerprint=:cleanup,"
                        + assignment
                        + " WHERE tenant_id=:tenant AND event_id=:event"
                    ),
                    params | {"receipt": receipt},
                )
        except SQLAlchemyError:
            raise ValueError("MEMORY_CLEANUP_STORE_UNAVAILABLE") from None

    async def scrub(
        self,
        event: MemoryInvalidation,
        dependencies: tuple[SourceDependency, ...],
        record: MemoryExecutionRecord,
    ) -> str | None:
        if record.runtime_kind not in {"OPERATIONS", "CUSTOMER_SERVICE"}:
            return None
        params = self._parameters(event, dependencies)
        try:
            async with self.engine.begin() as connection:
                execution = (
                    (
                        await connection.execute(
                            text(
                                "SELECT state,runtime_id,execution_revision,grant_epoch,source_epoch,deletion_epoch FROM agent_memory_execution WHERE tenant_id=:tenant AND execution_id=:execution FOR UPDATE"
                            ),
                            params,
                        )
                    )
                    .mappings()
                    .first()
                )
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM agent_memory_invalidation_receipt WHERE tenant_id=:tenant AND event_id=:event FOR UPDATE"
                            ),
                            params,
                        )
                    )
                    .mappings()
                    .first()
                )
                self._check(row, params)
                assert row is not None
                if (
                    execution is None
                    or bytes(execution["runtime_id"]).decode() != record.runtime_id
                    or not row["stop_confirmed"]
                    or row["threads_receipt"] is None
                ):
                    raise ValueError("MEMORY_CLEANUP_PROOF_REQUIRED")
                if execution["state"] == "SCRUBBED":
                    await self._verify_refresh_erasure(connection,params)
                    return row["scrub_receipt"]
                if execution["state"] != "REVOKED":
                    raise ValueError("MEMORY_REVOCATION_NOT_PERSISTED")
                if tuple(
                    execution[key]
                    for key in (
                        "execution_revision",
                        "grant_epoch",
                        "source_epoch",
                        "deletion_epoch",
                    )
                ) != (
                    row["expected_execution_revision"],
                    row["grant_epoch"],
                    row["source_epoch"],
                    row["deletion_epoch"],
                ):
                    raise ValueError("MEMORY_CLEANUP_CONFLICT_409")
                if (
                    self.runtime_scrubber is None
                    or not await self.runtime_scrubber(record)
                ):
                    return None
                if record.runtime_kind == "OPERATIONS":
                    runtime_params = {
                        "tenant": event.tenant_id,
                        "runtime": record.runtime_id,
                    }
                    runtime = (
                        (
                            await connection.execute(
                                text(
                                    "SELECT state_json,status,version FROM agent_run WHERE tenant_id=:tenant AND run_id=:runtime FOR UPDATE"
                                ),
                                runtime_params,
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if runtime is None or str(runtime["status"]).upper() not in {
                        "COMPLETED",
                        "SUCCEEDED",
                        "FAILED",
                        "CANCELLED",
                        "EXPIRED",
                    }:
                        raise ValueError("MEMORY_STOP_PENDING")
                    raw = (
                        json.loads(runtime["state_json"])
                        if isinstance(runtime["state_json"], str)
                        else runtime["state_json"]
                    )
                    request = raw["request"]
                    if (
                        request["tenant_id"] != event.tenant_id
                        or request["user_id"] != record.context.packet.scope.user_id
                        or raw["run_id"] != record.runtime_id
                        or request["metadata"]
                        .get("memory_execution", {})
                        .get("execution_id")
                        != event.execution_id
                    ):
                        raise ValueError("MEMORY_CLEANUP_CONFLICT_409")
                    retained = {
                        key: raw[key]
                        for key in (
                            "run_id",
                            "status",
                            "strategy",
                            "budget",
                            "budget_state",
                            "usage",
                        )
                    }
                    retained.update(
                        memory_scrubbed=True,
                        version=runtime["version"] + 1,
                        request={
                            key: request[key]
                            for key in ("request_id", "tenant_id", "user_id")
                        },
                        request_fingerprint=record.request_fingerprint,
                    )
                    await connection.execute(
                        text(
                            "UPDATE agent_run SET state_json=CAST(:body AS JSON),version=version+1 WHERE tenant_id=:tenant AND run_id=:runtime AND version=:version"
                        ),
                        runtime_params
                        | {"body": json.dumps(retained), "version": runtime["version"]},
                    )
                    await connection.execute(
                        text(
                            "UPDATE agent_run_event SET event_json=JSON_OBJECT('event_id',JSON_EXTRACT(event_json,'$.event_id'),'event_type',JSON_EXTRACT(event_json,'$.event_type'),'run_id',JSON_EXTRACT(event_json,'$.run_id'),'tenant_id',JSON_EXTRACT(event_json,'$.tenant_id'),'sequence',JSON_EXTRACT(event_json,'$.sequence'),'occurred_at_epoch_ms',JSON_EXTRACT(event_json,'$.occurred_at_epoch_ms'),'status',JSON_EXTRACT(event_json,'$.status'),'payload',JSON_OBJECT('memory_scrubbed',TRUE)) WHERE tenant_id=:tenant AND run_id=:runtime"
                        ),
                        runtime_params,
                    )
                receipt = "memory-snapshot-" + uuid4().hex
                await connection.execute(
                    text(
                        "UPDATE agent_memory_invalidation_receipt SET scrub_receipt=:receipt WHERE tenant_id=:tenant AND event_id=:event"
                    ),
                    params | {"receipt": receipt},
                )
                packet = record.context.packet
                authority = {
                    "schema_version": "memory-scrub-authority/1",
                    "scope": asdict(packet.scope),
                    "task_id": packet.task_id,
                    "execution_id": packet.execution_id,
                    "execution_revision": packet.execution_revision,
                    "original_epochs": [packet.grant_epoch, packet.source_epoch, packet.deletion_epoch],
                    "safety_dependencies": [
                        asdict(dep) for dep in packet.safety_dependencies
                    ],
                }
                if self.refresh_schema_required:
                    await connection.execute(
                        text("UPDATE agent_memory_context_refresh SET body_ciphertext=NULL,body_nonce=NULL,body_scrub_event_id=:event WHERE tenant_id=:tenant AND execution_id=:execution AND body_ciphertext IS NOT NULL"),params,
                    )
                await connection.execute(
                    text(
                        "UPDATE agent_memory_execution SET state='SCRUBBED',snapshot_ciphertext=NULL,snapshot_nonce=NULL,scrub_event_id=:event,scrub_authority=CAST(:authority AS JSON) WHERE tenant_id=:tenant AND execution_id=:execution"
                    ),
                    params | {"authority": json.dumps(authority)},
                )
                return receipt
        except SQLAlchemyError:
            raise ValueError("MEMORY_CLEANUP_STORE_UNAVAILABLE") from None
