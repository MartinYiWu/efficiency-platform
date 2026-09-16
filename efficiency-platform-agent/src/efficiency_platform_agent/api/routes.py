"""Run API 路由；仅依赖调用方注入的运行服务。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from efficiency_platform_agent.contracts.requests import (
    CancelRunRequestV1,
    CreateRunRequestV1,
    ResumeRunRequestV1,
)
from efficiency_platform_agent.contracts.responses import RunViewV1
from efficiency_platform_agent.harness.errors import HarnessError, normalize_error

from .sse import parse_last_event_id, render_events, stream_run_events

if TYPE_CHECKING:
    from efficiency_platform_agent.harness.service import AgentRuntimeService
    from efficiency_platform_agent.runtime.event_hub import EventHub


def _error_response(error: HarnessError, status_code: int) -> JSONResponse:
    """生成稳定且不含异常正文的错误响应。"""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": error.code,
                "category": error.category,
                "retryable": error.retryable,
                "safe_message": error.safe_message,
            }
        },
    )


def _status_for_error(error: HarnessError) -> int:
    """将 Harness 错误码映射为稳定 HTTP 状态码。"""
    if error.code in {"RUN_NOT_FOUND", "RESOURCE_NOT_FOUND"}:
        return status.HTTP_404_NOT_FOUND
    if error.code == "CONVERSATION_CAPACITY_EXCEEDED":
        return status.HTTP_429_TOO_MANY_REQUESTS
    if error.code in {
        "RUN_NOT_WAITING_INPUT",
        "CHECKPOINT_MISMATCH",
        "RUN_ALREADY_TERMINAL",
        "REQUEST_ID_CONFLICT",
        "STRATEGY_UNSUPPORTED",
        "GRAPH_NEXT_STATUS_FORBIDDEN",
    }:
        return status.HTTP_409_CONFLICT
    if error.code in {"TENANT_MISMATCH", "FORBIDDEN"}:
        return status.HTTP_403_FORBIDDEN
    if error.code in {
        "INVALID_EVENT_CURSOR",
        "INVALID_CONVERSATION_ID",
        "INVALID_TENANT",
        "INVALID_REQUEST",
        "RESUME_VALUE_INVALID",
        "UNKNOWN_SCENARIO",
    }:
        return status.HTTP_400_BAD_REQUEST
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def _tenant_matches(header_tenant: str, body_tenant: str) -> None:
    """拒绝请求头与请求体中的租户身份不一致。"""
    if header_tenant != body_tenant:
        raise HarnessError("TENANT_MISMATCH", "租户身份不匹配", category="request")


def build_router(
    service: AgentRuntimeService, event_hub: EventHub | None = None
) -> APIRouter:
    """构造绑定注入服务的 API 路由。"""
    router = APIRouter()

    @router.post(
        "/v1/runs", response_model=RunViewV1, status_code=status.HTTP_201_CREATED
    )
    async def create_run(
        request: CreateRunRequestV1,
        x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    ) -> RunViewV1:
        _tenant_matches(x_tenant_id, request.tenant_id)
        scheduler = getattr(service, "create_and_schedule", None)
        if scheduler is not None:
            return await scheduler(request)
        return await service.create_and_execute(request)

    @router.post("/v1/runs/{run_id}/resume", response_model=RunViewV1)
    async def resume_run(
        run_id: str,
        request: ResumeRunRequestV1,
        x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    ) -> RunViewV1:
        _tenant_matches(x_tenant_id, request.tenant_id)
        return await service.resume_run(run_id, request)

    @router.post("/v1/runs/{run_id}/cancel", response_model=RunViewV1)
    async def cancel_run(
        run_id: str,
        request: CancelRunRequestV1,
        x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    ) -> JSONResponse | RunViewV1:
        _tenant_matches(x_tenant_id, request.tenant_id)
        result = await service.cancel_run(run_id, request)
        if result.status.value == "running":
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=result.model_dump(mode="json"),
            )
        return result

    @router.get("/v1/runs/{run_id}", response_model=RunViewV1)
    async def get_run(
        run_id: str, x_tenant_id: str = Header(..., alias="X-Tenant-ID")
    ) -> RunViewV1:
        return await service.get_run(run_id, x_tenant_id)

    @router.get(
        "/v1/runs/{run_id}/events",
        response_class=StreamingResponse,
        responses={200: {"content": {"text/event-stream": {}}}},
    )
    async def list_run_events(
        run_id: str,
        request: Request,
        x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        try:
            after_sequence = parse_last_event_id(last_event_id)
        except ValueError as error:
            raise HarnessError(
                "INVALID_EVENT_CURSOR", "事件游标无效", category="request"
            ) from error
        if event_hub is not None:
            await service.get_run(run_id, x_tenant_id)
            return StreamingResponse(
                stream_run_events(
                    event_hub,
                    run_id,
                    after_sequence=after_sequence,
                    is_disconnected=request.is_disconnected,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
        events = await service.list_events(run_id, x_tenant_id, after_sequence)
        return StreamingResponse(
            (chunk.encode("utf-8") for chunk in render_events(events)),
            media_type="text/event-stream",
        )

    return router


async def handle_harness_error(_: Request, error: Exception) -> JSONResponse:
    """把 Harness 边界错误转为稳定正文。"""
    normalized = error if isinstance(error, HarnessError) else normalize_error(error)
    return _error_response(normalized, _status_for_error(normalized))


async def handle_unexpected_error(_: Request, error: Exception) -> JSONResponse:
    """归一化未知异常，避免内部正文或配置泄露。"""
    return _error_response(
        normalize_error(error), status.HTTP_500_INTERNAL_SERVER_ERROR
    )


__all__ = ["build_router", "handle_harness_error", "handle_unexpected_error"]
