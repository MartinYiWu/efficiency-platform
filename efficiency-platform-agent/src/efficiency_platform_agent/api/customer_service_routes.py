"""独立智能客服内部 API。"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from efficiency_platform_agent.agents.customer_service.service import (
    CustomerServiceNotFoundError,
    CustomerServiceRunService,
)
from efficiency_platform_agent.agents.customer_service.state import (
    CustomerServiceRunRequest,
    DebugRequest,
)


def build_customer_service_router(service: CustomerServiceRunService) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/customer-service/conversations/{conversation_id}/messages", status_code=202)
    async def submit(conversation_id: UUID, body: CustomerServiceRunRequest) -> dict[str, object]:
        if body.conversation_id != conversation_id:
            raise HTTPException(422, detail="conversation_id 不一致")
        return (await service.submit(body)).model_dump(mode="json")

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
                yield "event: error\ndata: {\"error_code\":\"RUN_NOT_FOUND\"}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @router.post("/v1/customer-service/runs/{run_id}/cancel")
    async def cancel(run_id: UUID) -> dict[str, object]:
        try:
            return (await service.cancel(run_id)).model_dump(mode="json")
        except CustomerServiceNotFoundError as error:
            raise HTTPException(404, detail="Run 不存在") from error

    @router.post("/internal/v1/customer-service/rag-debug-runs")
    async def debug(body: DebugRequest) -> dict[str, object]:
        try:
            return await service.debug(body)
        except CustomerServiceNotFoundError as error:
            raise HTTPException(404, detail=str(error)) from error

    return router


__all__ = ["build_customer_service_router"]
