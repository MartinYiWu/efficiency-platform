"""显式注入后才挂载的 X04 内部真实验收入口。"""

from __future__ import annotations

from fastapi import APIRouter, Header

from efficiency_platform_agent.contracts.live_acceptance_v2 import (
    LiveAcceptanceRequestV1,
    LiveAcceptanceViewV1,
)
from efficiency_platform_agent.harness.errors import HarnessError
from efficiency_platform_agent.harness.live_acceptance import (
    LiveAcceptanceError,
    LiveAcceptanceService,
)

_FORBIDDEN_REASONS = frozenset(
    {
        "LIVE_ACTION_NOT_AUTHORIZED",
        "LIVE_AUTHORIZATION_EXPIRED",
        "LIVE_AUTHORIZATION_NOT_FOUND",
        "LIVE_AUTHORIZATION_REUSED",
        "LIVE_BUDGET_NOT_AUTHORIZED",
        "LIVE_CASE_NOT_AUTHORIZED",
        "LIVE_TENANT_NOT_AUTHORIZED",
    }
)


def build_live_acceptance_router(service: LiveAcceptanceService) -> APIRouter:
    """构造不接受客户端创建授权或预算策略的内部路由。"""

    router = APIRouter()

    @router.post(
        "/v1/internal/research-v2/live-acceptance",
        response_model=LiveAcceptanceViewV1,
    )
    async def execute_live_acceptance(
        request: LiveAcceptanceRequestV1,
        x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    ) -> LiveAcceptanceViewV1:
        try:
            return await service.execute(request, tenant_id=x_tenant_id)
        except LiveAcceptanceError as exc:
            if exc.reason_code in _FORBIDDEN_REASONS:
                raise HarnessError(
                    "FORBIDDEN",
                    "真实验收授权不允许本次请求",
                    category="request",
                ) from exc
            if exc.reason_code == "LIVE_REQUEST_ID_CONFLICT":
                raise HarnessError(
                    "REQUEST_ID_CONFLICT",
                    "request_id 已用于其他验收参数",
                    category="request",
                ) from exc
            raise HarnessError(
                "INVALID_REQUEST",
                "真实验收请求无效",
                category="request",
            ) from exc

    return router


__all__ = ["build_live_acceptance_router"]
