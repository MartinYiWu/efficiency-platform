"""智能客服不可变 Release Bundle 内部接口。"""

from __future__ import annotations

import json
from collections.abc import Callable, Coroutine
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute

from efficiency_platform_agent.agents.customer_service.release_bundle import (
    CustomerServiceReleaseBundle,
    ReleaseAck,
    ReleaseChecksumError,
)
from efficiency_platform_agent.agents.customer_service.release_repository import (
    ReleaseConflictError,
)


class ReleaseRepository(Protocol):
    async def save(
        self, release_id: UUID, bundle: CustomerServiceReleaseBundle
    ) -> CustomerServiceReleaseBundle: ...


class ReleaseJsonRequest(Request):
    async def json(self) -> Any:
        # 摘要核验前不能经过二进制浮点解码，否则合法的数据库精度会丢失。
        return json.loads(await self.body(), parse_float=Decimal)


class ReleaseJsonRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            return await handler(ReleaseJsonRequest(request.scope, request.receive))

        return handle


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "category": "request",
                "retryable": False,
                "safe_message": message,
            }
        },
    )


def build_customer_service_release_router(
    repository: ReleaseRepository,
) -> APIRouter:
    router = APIRouter(
        prefix="/internal/v1/customer-service", route_class=ReleaseJsonRoute
    )

    @router.put(
        "/releases/{release_id}",
        response_model=ReleaseAck,
        responses={409: {}, 422: {}},
    )
    async def publish_release(
        release_id: UUID, bundle: CustomerServiceReleaseBundle
    ) -> ReleaseAck | JSONResponse:
        try:
            bundle.assert_checksum()
            saved = await repository.save(release_id, bundle)
        except ReleaseChecksumError:
            return _error(422, "CS_AGENT_RELEASE_CHECKSUM_INVALID", "Release 校验失败")
        except ReleaseConflictError:
            return _error(409, "CS_AGENT_RELEASE_CONFLICT", "Release ID 已存在不同内容")
        return ReleaseAck(release_id=release_id, checksum=saved.snapshot_checksum)

    return router


__all__ = ["build_customer_service_release_router"]
