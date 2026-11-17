"""独立智能客服内部 API。"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from efficiency_platform_agent.agents.customer_service.service import (
    CustomerServiceNotFoundError,
    CustomerServiceRunService,
    CustomerServiceScopeError,
)
from efficiency_platform_agent.agents.customer_service.state import (
    CustomerServiceRunRequest,
    DebugRequest,
)
from efficiency_platform_agent.core.run_context_binding import bind_conversation_scope

from .context_auth import InternalAuthorizer, authorize_memory_context


def build_customer_service_router(
    service: CustomerServiceRunService,
    authorize: InternalAuthorizer | None = None,
    *,
    memory_enabled: bool = False,
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/v1/customer-service/conversations/{conversation_id}/messages", status_code=202
    )
    async def submit(
        conversation_id: UUID, request: Request, body: CustomerServiceRunRequest
    ) -> dict[str, object]:
        if body.conversation_id != conversation_id:
            raise HTTPException(422, detail="conversation_id 不一致")
        scope = await authorize_memory_context(
            request,
            body.memory_context,
            authorize,
            tenant=body.tenant_id,
            user=body.user_id,
            domain="customer-service",
            session_id=str(conversation_id),
            memory_enabled=memory_enabled,
        )
        with bind_conversation_scope(
            scope, memory_context=body.memory_context.to_core()
        ):
            try:
                return (await service.submit(body)).model_dump(mode="json")
            except CustomerServiceScopeError as error:
                raise HTTPException(409, detail="CONTEXT_SCOPE_MISMATCH") from error

    @router.get("/v1/customer-service/runs/{run_id}/events")
    async def events(
        run_id: UUID,
        after_sequence: int = Query(default=0, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        if last_event_id is not None:
            try:
                after_sequence = max(after_sequence, int(last_event_id))
            except ValueError as error:
                raise HTTPException(422, detail="Last-Event-ID 无效") from error

        async def stream():
            try:
                async for event in service.events(run_id, after_sequence):
                    value = event.model_dump(mode="json")
                    yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {json.dumps(value, ensure_ascii=False)}\n\n"
            except CustomerServiceNotFoundError:
                yield 'event: error\ndata: {"error_code":"RUN_NOT_FOUND"}\n\n'

        return StreamingResponse(stream(), media_type="text/event-stream")

    @router.post("/v1/customer-service/runs/{run_id}/cancel")
    async def cancel(run_id: UUID) -> dict[str, object]:
        try:
            return (await service.cancel(run_id)).model_dump(mode="json")
        except CustomerServiceNotFoundError as error:
            raise HTTPException(404, detail="Run 不存在") from error

    @router.post("/internal/v1/customer-service/rag-debug-runs")
    async def debug(request: Request, body: DebugRequest) -> dict[str, object]:
        scope = await authorize_memory_context(
            request,
            body.memory_context,
            authorize,
            tenant=body.tenant_id,
            user=body.memory_context.scope.user_id if body.memory_context.scope else "",
            domain="customer-service",
            session_id=None,
            session_kind="TASK_ONLY",
            memory_enabled=memory_enabled,
        )
        try:
            with bind_conversation_scope(
                scope, memory_context=body.memory_context.to_core()
            ):
                return await service.debug(body)
        except CustomerServiceScopeError as error:
            raise HTTPException(409, detail="CONTEXT_SCOPE_MISMATCH") from error
        except CustomerServiceNotFoundError as error:
            raise HTTPException(404, detail=str(error)) from error

    return router


__all__ = ["build_customer_service_router"]
