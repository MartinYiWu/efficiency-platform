"""Java单向失效入口；先持久禁用授权，再实际停止本地运行，不能确认其他清理目标。"""

import asyncio
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, field_validator

from efficiency_platform_agent.contracts.context_control import ContextManifestModel
from efficiency_platform_agent.contracts.memory import SourceDependencyModel
from efficiency_platform_agent.core.context_control import ContextManifest
from efficiency_platform_agent.core.memory import SourceDependency
from efficiency_platform_agent.core.memory_cleanup import MemoryCleanupJournal
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionRecord,
    MemoryExecutionStore,
    MemoryInvalidation,
)
from efficiency_platform_agent.core.memory_thread import (
    ResumeReceipt,
    ResumeRequest,
    ThreadCleanupReceipt,
)


class InvalidationRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )
    event_id: str
    expected_execution_revision: int
    grant_epoch: int
    source_epoch: int
    deletion_epoch: int


class CleanupRequest(InvalidationRequest):
    source_dependencies: tuple[SourceDependencyModel, ...]

    @field_validator("source_dependencies", mode="before")
    @classmethod
    def freeze_dependencies(cls, value):
        return tuple(value) if isinstance(value, list) else value


class ResumeBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )
    wait_event_id: str
    packet_revision: int
    expected_execution_revision: int
    resume_request_id: str
    operation_hash: str
    mode: str
    new_content: bool = False


def build_memory_router(
    store: MemoryExecutionStore,
    authorize: Callable[[Request], Awaitable[str]],
    stop: Callable[[MemoryExecutionRecord], Awaitable[None]],
    manifests: Callable[[str, str], Awaitable[tuple[ContextManifest, ...]]]
    | None = None,
    erase_threads: Callable[
        [str, str, str, int, tuple[SourceDependency, ...]],
        Awaitable[ThreadCleanupReceipt],
    ]
    | None = None,
    cleanup_journal: MemoryCleanupJournal | None = None,
    resume_execution: Callable[[str, str, ResumeRequest], Awaitable[ResumeReceipt]]
    | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/internal/v1/memory/executions/{execution_id}/manifest")
    async def manifest(execution_id: str, request: Request) -> dict[str, object]:
        try:
            tenant = await authorize(request)
        except PermissionError:
            raise HTTPException(401, detail="CONTEXT_INTERNAL_AUTH_REQUIRED") from None
        if tenant != request.headers.get("X-Tenant-ID"):
            raise HTTPException(403, detail="CONTEXT_SCOPE_MISMATCH")
        record = await store.get(tenant, execution_id)
        if record is None or record.state != "ACTIVE":
            raise HTTPException(409, detail="MEMORY_ACCESS_REVOKED")
        if manifests is None:
            raise HTTPException(503, detail="MEMORY_MANIFEST_STORE_REQUIRED")
        actual = await manifests(tenant, execution_id)
        if any(
            item.scope.conversation != record.context.packet.scope
            or item.packet_id != record.context.packet.packet_id
            or item.packet_revision != record.context.packet.packet_revision
            for item in actual
        ):
            raise HTTPException(409, detail="MEMORY_MANIFEST_BINDING_INVALID")
        return {
            "runtime_id": record.runtime_id,
            "execution_id": execution_id,
            "packet_id": record.context.packet.packet_id,
            "packet_revision": record.context.packet.packet_revision,
            "manifests": [
                ContextManifestModel.from_core(item).model_dump(mode="json")
                for item in actual
            ],
        }

    @router.post("/internal/v1/memory/executions/{execution_id}/invalidate")
    async def invalidate(
        execution_id: str, request: Request, body: InvalidationRequest
    ) -> dict[str, object]:
        try:
            tenant = await authorize(request)
        except PermissionError:
            raise HTTPException(401, detail="CONTEXT_INTERNAL_AUTH_REQUIRED") from None
        if tenant != request.headers.get("X-Tenant-ID"):
            raise HTTPException(403, detail="CONTEXT_SCOPE_MISMATCH")
        try:
            event = MemoryInvalidation(tenant, execution_id, **body.model_dump())
            receipt = await store.invalidate(event)
            record = await store.get(tenant, execution_id)
            if record is None or record.state != "REVOKED":
                raise ValueError("MEMORY_REVOCATION_NOT_PERSISTED")
            try:
                async with asyncio.timeout(10):
                    await stop(record)
            except TimeoutError:
                raise ValueError("MEMORY_STOP_PENDING") from None
            return {
                "execution_id": execution_id,
                "event_id": body.event_id,
                "receipt_ref": receipt,
                "target": "AGENT_STOP",
            }
        except ValueError as error:
            code = str(error)
            status = (
                404
                if code == "MEMORY_EXECUTION_NOT_FOUND"
                else 409
                if code.endswith("_409")
                else 503
            )
            raise HTTPException(
                status,
                detail=code
                if code.startswith("MEMORY_")
                else "MEMORY_STOP_UNAVAILABLE",
            ) from None

    @router.post("/internal/v1/memory/executions/{execution_id}/cleanup")
    async def cleanup(
        execution_id: str, request: Request, body: CleanupRequest
    ) -> dict[str, object]:
        try:
            tenant = await authorize(request)
        except PermissionError:
            raise HTTPException(401, detail="CONTEXT_INTERNAL_AUTH_REQUIRED") from None
        if tenant != request.headers.get("X-Tenant-ID"):
            raise HTTPException(403, detail="CONTEXT_SCOPE_MISMATCH")
        try:
            dependencies = tuple(dep.to_core() for dep in body.source_dependencies)
            event = MemoryInvalidation(
                tenant, execution_id, **body.model_dump(exclude={"source_dependencies"})
            )
            receipts = (
                await cleanup_journal.receipts(event, dependencies)
                if cleanup_journal is not None
                else {}
            )
            if {"AGENT_STOP", "THREADS", "SNAPSHOT"}.issubset(receipts):
                return {
                    "execution_id": execution_id,
                    "event_id": body.event_id,
                    "deletion_epoch": body.deletion_epoch,
                    "receipts": receipts,
                }
            record = await store.get(tenant, execution_id)
            if record is None:
                raise ValueError("MEMORY_EXECUTION_NOT_FOUND")
            if not dependencies or not set(dependencies).issubset(
                record.context.packet.safety_dependencies
            ):
                raise ValueError("MEMORY_CLEANUP_SCOPE_409")
            receipt = await cleanup_journal.revoke(event, dependencies, record) if cleanup_journal is not None else await store.invalidate(event)
            record = await store.get(tenant, execution_id)
            if record is None or record.state != "REVOKED":
                raise ValueError("MEMORY_REVOCATION_NOT_PERSISTED")
            if "AGENT_STOP" not in receipts:
                try:
                    async with asyncio.timeout(10):
                        await stop(record)
                except TimeoutError:
                    raise ValueError("MEMORY_STOP_PENDING") from None
                if cleanup_journal is not None:
                    await cleanup_journal.confirm(
                        event, dependencies, "AGENT_STOP", receipt
                    )
                receipts["AGENT_STOP"] = receipt
            if erase_threads is not None and "THREADS" not in receipts:
                result = await erase_threads(
                    tenant,
                    execution_id,
                    body.event_id,
                    body.expected_execution_revision,
                    dependencies,
                )
                if result.status == "DELETED" and result.receipt_ref is not None:
                    if cleanup_journal is not None:
                        await cleanup_journal.confirm(
                            event, dependencies, "THREADS", result.receipt_ref
                        )
                    receipts["THREADS"] = result.receipt_ref
            if cleanup_journal is not None and "THREADS" in receipts:
                scrub = await cleanup_journal.scrub(event, dependencies, record)
                if scrub is not None:
                    receipts["SNAPSHOT"] = scrub
            return {
                "execution_id": execution_id,
                "event_id": body.event_id,
                "deletion_epoch": body.deletion_epoch,
                "receipts": receipts,
            }
        except ValueError as error:
            code = str(error)
            raise HTTPException(
                404
                if code == "MEMORY_EXECUTION_NOT_FOUND"
                else 409
                if code.endswith("_409")
                else 503,
                detail=code
                if code.startswith("MEMORY_")
                else "MEMORY_CLEANUP_UNAVAILABLE",
            ) from None

    @router.post("/internal/v1/memory/executions/{execution_id}/resume")
    async def resume(
        execution_id: str, request: Request, body: ResumeBody
    ) -> dict[str, str]:
        try:
            tenant = await authorize(request)
        except PermissionError:
            raise HTTPException(401, detail="CONTEXT_INTERNAL_AUTH_REQUIRED") from None
        if tenant != request.headers.get("X-Tenant-ID"):
            raise HTTPException(403, detail="CONTEXT_SCOPE_MISMATCH")
        if resume_execution is None:
            raise HTTPException(503, detail="MEMORY_RESUME_GATE_REQUIRED")
        try:
            command = ResumeRequest(**body.model_dump())
            record = await store.get(tenant, execution_id)
            if record is None or record.state != "ACTIVE":
                raise ValueError("MEMORY_ACCESS_REVOKED")
            receipt = await resume_execution(record.runtime_id, tenant, command)
            return {"code": receipt.code, "receipt_ref": receipt.receipt_ref}
        except (ValueError, PermissionError):
            raise HTTPException(409, detail="MEMORY_RESUME_REJECTED") from None

    return router
