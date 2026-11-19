"""Java单向失效入口；先持久禁用授权，再实际停止本地运行，不能确认其他清理目标。"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from efficiency_platform_agent.contracts.context_control import ContextManifestModel
from efficiency_platform_agent.contracts.memory import SourceDependencyModel
from efficiency_platform_agent.contracts.memory_refresh import (
    MemoryContextResumeModel,
    MemoryContextResumeReceiptModel,
    MemoryContextWaitModel,
)
from efficiency_platform_agent.core.context_control import ContextManifest
from efficiency_platform_agent.core.memory import SourceDependency, require_id
from efficiency_platform_agent.core.memory_cleanup import MemoryCleanupJournal
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionRecord,
    MemoryExecutionStore,
    MemoryInvalidation,
)
from efficiency_platform_agent.core.memory_refresh import (
    MemoryContextRefreshPort,
    ResumeCode,
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


class DeriveFinishBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )
    plan_id: str
    plan_fingerprint: str
    status: Literal["COMMITTED", "REJECTED"]


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
    refresh_service: MemoryContextRefreshPort | None = None,
    memory_derive_coordinator: Any | None = None,
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
        for item in actual:
            if (
                item.scope.conversation != record.context.packet.scope
                or item.packet_id != record.context.packet.packet_id
            ):
                raise HTTPException(409, detail="MEMORY_MANIFEST_BINDING_INVALID")
            if refresh_service is None:
                valid = item.packet_revision == record.context.packet.packet_revision
            else:
                try:
                    valid = await refresh_service.validate_execution_manifest(
                        item, record
                    )
                except (ValueError, PermissionError):
                    raise HTTPException(
                        503, detail="MEMORY_AUTHORITY_UNAVAILABLE"
                    ) from None
            if not valid:
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
            receipt = (
                await cleanup_journal.revoke(event, dependencies, record)
                if cleanup_journal is not None
                else await store.invalidate(event)
            )
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

    async def refresh_actor(request: Request) -> str:
        try:
            tenant = await authorize(request)
        except PermissionError:
            raise HTTPException(401, detail="CONTEXT_INTERNAL_AUTH_REQUIRED") from None
        if tenant != request.headers.get("X-Tenant-ID"):
            raise HTTPException(403, detail="CONTEXT_SCOPE_MISMATCH")
        return tenant

    async def derive_record(request: Request, execution_id: str):
        tenant = await refresh_actor(request)
        if memory_derive_coordinator is None:
            raise HTTPException(503, detail="MEMORY_DERIVE_FEATURE_DISABLED")
        record = await store.get(tenant, execution_id)
        if record is None:
            raise HTTPException(404, detail="MEMORY_EXECUTION_NOT_FOUND")
        if record.state != "ACTIVE":
            raise HTTPException(409, detail="MEMORY_ACCESS_REVOKED")
        return tenant, record, memory_derive_coordinator

    @router.get("/internal/v1/memory/executions/{execution_id}/derive-plan")
    async def derive_plan(execution_id: str, request: Request):
        tenant, record, coordinator = await derive_record(request, execution_id)
        try:
            pending = await coordinator.pending(tenant, execution_id)
            if pending is None:
                raise HTTPException(404, detail="DERIVE_ORIGINAL_FRAME_REQUIRED")
            if (
                pending.runtime_id != record.runtime_id
                or pending.execution_scope.conversation.to_core()
                != record.context.packet.scope
            ):
                raise PermissionError("DERIVE_SCOPE_MISMATCH")
            return pending.model_dump(mode="json")
        except (ValueError, PermissionError):
            raise HTTPException(409, detail="DERIVE_ORIGINAL_FRAME_REQUIRED") from None

    @router.post("/internal/v1/memory/executions/{execution_id}/derive-finish")
    async def derive_finish(
        execution_id: str, request: Request, body: DeriveFinishBody
    ):
        tenant, _, coordinator = await derive_record(request, execution_id)
        try:
            require_id(body.plan_id)
            if len(body.plan_fingerprint) != 64 or any(
                c not in "0123456789abcdef" for c in body.plan_fingerprint
            ):
                raise ValueError("DERIVE_BINDING_CONFLICT")
            await coordinator.finish(
                tenant, execution_id, body.plan_id, body.plan_fingerprint, body.status
            )
            return {"code": "MEMORY_DERIVE_FINISHED"}
        except (ValueError, PermissionError):
            raise HTTPException(409, detail="DERIVE_BINDING_CONFLICT") from None

    def refresh_error(error: ValueError | PermissionError) -> HTTPException:
        value = str(error)
        if value == "MEMORY_ACCESS_REVOKED":
            value = "ACCESS_REVOKED"
        try:
            code = ResumeCode(value)
        except ValueError:
            return HTTPException(503, detail="MEMORY_AUTHORITY_UNAVAILABLE")
        return HTTPException(code.http_status, detail=code.value)

    @router.get("/internal/v1/memory/executions/{execution_id}/wait")
    async def context_wait(
        execution_id: str, request: Request, wait_event_id: str | None = None
    ):
        tenant = await refresh_actor(request)
        if refresh_service is None:
            raise HTTPException(503, detail="MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        try:
            require_id(execution_id)
            if wait_event_id is not None:
                require_id(wait_event_id)
        except (ValueError, TypeError):
            raise HTTPException(422, detail="INVALID_SCHEMA") from None
        try:
            record = await store.get(tenant, execution_id)
            if record is None:
                raise HTTPException(404, detail="MEMORY_EXECUTION_NOT_FOUND")
            if record.state != "ACTIVE":
                raise ValueError("ACCESS_REVOKED")
            wait = (
                await refresh_service.get_wait(
                    record.context.packet.scope, execution_id, wait_event_id
                )
                if wait_event_id is not None
                else await refresh_service.get_wait(
                    record.context.packet.scope, execution_id
                )
            )
            if wait is None:
                raise HTTPException(404, detail="MEMORY_WAIT_NOT_FOUND")
            if (
                wait.execution_id != execution_id
                or wait.scope != record.context.packet.scope
                or wait.runtime_id != record.runtime_id
            ):
                raise ValueError("CONTEXT_SCOPE_MISMATCH")
            return MemoryContextWaitModel.model_validate_json(
                json.dumps(asdict(wait))
            ).model_dump(mode="json")
        except (ValueError, PermissionError) as error:
            raise refresh_error(error) from None

    @router.post("/internal/v1/memory/executions/{execution_id}/resume")
    async def resume(execution_id: str, request: Request):
        tenant = await refresh_actor(request)
        raw = await request.body()
        if len(raw) > 1_000_000:
            raise HTTPException(422, detail="INVALID_SCHEMA")
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise TypeError
            if "contract_version" in parsed:
                command = MemoryContextResumeModel.model_validate_json(raw).to_core()
            else:
                command = None
                body = ResumeBody.model_validate_json(raw)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, detail="INVALID_SCHEMA") from None
        if command is not None:
            if refresh_service is None:
                raise HTTPException(503, detail="MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
            try:
                record = await store.get(tenant, execution_id)
                if record is None:
                    raise HTTPException(404, detail="MEMORY_EXECUTION_NOT_FOUND")
                if record.state != "ACTIVE":
                    raise ValueError("ACCESS_REVOKED")
                receipt = await refresh_service.resume(
                    record.context.packet.scope, execution_id, command
                )
                result = MemoryContextResumeReceiptModel.model_validate_json(
                    json.dumps(asdict(receipt))
                )
                if (
                    result.wait_event_id != command.wait_event_id
                    or result.execution_revision != command.expected_execution_revision
                ):
                    raise ValueError("MEMORY_RESUME_CONFLICT")
                return JSONResponse(
                    status_code=receipt.code.http_status,
                    content=result.model_dump(mode="json"),
                )
            except (ValueError, PermissionError) as error:
                raise refresh_error(error) from None
        if resume_execution is None:
            raise HTTPException(503, detail="MEMORY_RESUME_GATE_REQUIRED")
        try:
            legacy_command = ResumeRequest(**body.model_dump())
            record = await store.get(tenant, execution_id)
            if record is None or record.state != "ACTIVE":
                raise ValueError("MEMORY_ACCESS_REVOKED")
            legacy_receipt = await resume_execution(
                record.runtime_id, tenant, legacy_command
            )
            return {
                "code": legacy_receipt.code,
                "receipt_ref": legacy_receipt.receipt_ref,
            }
        except (ValueError, PermissionError):
            raise HTTPException(409, detail="MEMORY_RESUME_REJECTED") from None

    return router
