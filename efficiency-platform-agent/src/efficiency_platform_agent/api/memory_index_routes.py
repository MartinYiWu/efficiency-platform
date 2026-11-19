"""内部受控索引入口；不签发预算，不返回正文。"""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from efficiency_platform_agent.contracts.memory_index import (
    MemoryIndexDeleteBody,
    MemoryIndexExpiryBody,
    MemoryIndexUpsertBody,
    MemoryRecallBody,
)
from efficiency_platform_agent.core.paid_budget import PaidBudgetError


def build_memory_index_router(runtime, authorize) -> APIRouter:
    router = APIRouter()

    async def parse(request, model):
        try:
            tenant = await authorize(request)
        except PermissionError:
            raise HTTPException(401, detail="CONTEXT_INTERNAL_AUTH_REQUIRED") from None
        if tenant != request.headers.get("X-Tenant-ID"):
            raise HTTPException(403, detail="CONTEXT_SCOPE_MISMATCH")
        raw = await request.body()
        if len(raw) > 2_000_000:
            raise HTTPException(413, detail="MEMORY_INDEX_REQUEST_TOO_LARGE")
        try:
            value = model.model_validate_json(raw)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, detail="MEMORY_INDEX_REQUEST_INVALID") from None
        scope = (
            value.authorization.scope
            if isinstance(value, MemoryRecallBody)
            else value.scope
        )
        if scope.tenant_id != tenant:
            raise HTTPException(403, detail="CONTEXT_SCOPE_MISMATCH")
        return value

    async def invoke(work):
        try:
            return await work()
        except (PermissionError, ValueError, PaidBudgetError) as error:
            code = error.code if isinstance(error, PaidBudgetError) else str(error)
            if not code.startswith(
                (
                    "MEMORY_",
                    "TASK_",
                    "AGENT_",
                    "CONTINUATION_",
                    "BUDGET_",
                    "NO_BUDGET",
                    "PROVIDER_",
                )
            ):
                code = "MEMORY_INDEX_UNAVAILABLE"
            raise HTTPException(409, detail=code) from None

    @router.post("/internal/v1/memory/index/upsert")
    async def upsert(request: Request):
        body = await parse(request, MemoryIndexUpsertBody)
        return await invoke(lambda: runtime.upsert(body.to_core()))

    @router.post("/internal/v1/memory/index/delete")
    async def delete(request: Request):
        body = await parse(request, MemoryIndexDeleteBody)
        return await invoke(lambda: runtime.delete(body.to_core()))

    @router.post("/internal/v1/memory/index/recall")
    async def recall(request: Request):
        body = await parse(request, MemoryRecallBody)

        async def work():
            return asdict(
                await runtime.recall(
                    body.authorization, terms=body.terms, query=body.query
                )
            )

        return await invoke(work)

    @router.post("/internal/v1/memory/index/expire")
    async def expire(request: Request):
        body = await parse(request, MemoryIndexExpiryBody)
        return await invoke(lambda: runtime.expire(body.scope, limit=body.limit))

    return router
