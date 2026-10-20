"""FastAPI 应用工厂；不在导入时创建运行时全局实例。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from efficiency_platform_agent.harness.errors import HarnessError

from .routes import build_router, handle_harness_error, handle_unexpected_error
from .uploads import build_upload_router

if TYPE_CHECKING:
    from efficiency_platform_agent.capabilities.customer_service_ingest import (
        CustomerServiceIngestPort,
    )
    from efficiency_platform_agent.capabilities.document.service import (
        DocumentIngestionService,
    )
    from efficiency_platform_agent.conversation.service import ConversationService
    from efficiency_platform_agent.harness.live_acceptance import (
        LiveAcceptanceService,
    )
    from efficiency_platform_agent.harness.service import AgentRuntimeService
    from efficiency_platform_agent.runtime.event_hub import EventHub


def create_app(
    service: AgentRuntimeService,
    *,
    document_service: DocumentIngestionService | None = None,
    event_hub: EventHub | None = None,
    conversation_service: ConversationService | None = None,
    live_acceptance_service: LiveAcceptanceService | None = None,
    customer_service_ingest_service: CustomerServiceIngestPort | None = None,
    customer_service_release_repository: object | None = None,
    customer_service_run_service: object | None = None,
    runtime_mode: str = "s2_fake_in_memory",
    dependency_probe: Callable[[], Awaitable[None]] | None = None,
) -> FastAPI:
    """创建绑定运行服务并可选挂载文档摄取服务的 FastAPI 应用。"""
    app = FastAPI(title="Efficiency Platform Agent Runtime", version="s2")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5190", "http://localhost:5190"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Last-Event-ID", "X-Tenant-ID"],
        allow_credentials=False,
    )
    app.state.runtime_service = service
    resolved_event_hub = event_hub or getattr(service, "event_hub", None)
    app.state.event_hub = resolved_event_hub
    app.include_router(build_router(service, resolved_event_hub))
    if conversation_service is not None:
        from .conversation_routes import build_conversation_router

        app.state.conversation_service = conversation_service
        app.include_router(build_conversation_router(conversation_service))
    if document_service is not None:
        app.include_router(build_upload_router(document_service))
    if live_acceptance_service is not None:
        from .live_acceptance_routes import build_live_acceptance_router

        app.state.live_acceptance_service = live_acceptance_service
        app.include_router(build_live_acceptance_router(live_acceptance_service))
    if customer_service_ingest_service is not None:
        from .customer_service_ingest_routes import (
            build_customer_service_ingest_router,
        )

        app.state.customer_service_ingest_service = customer_service_ingest_service
        app.include_router(
            build_customer_service_ingest_router(customer_service_ingest_service)
        )
    if customer_service_release_repository is not None:
        from .customer_service_release_routes import (
            build_customer_service_release_router,
        )

        app.state.customer_service_release_repository = (
            customer_service_release_repository
        )
        app.include_router(
            build_customer_service_release_router(
                customer_service_release_repository  # type: ignore[arg-type]
            )
        )
    if customer_service_run_service is not None:
        from .customer_service_routes import build_customer_service_router

        app.state.customer_service_run_service = customer_service_run_service
        app.include_router(
            build_customer_service_router(customer_service_run_service)  # type: ignore[arg-type]
        )
    app.add_exception_handler(HarnessError, handle_harness_error)
    app.add_exception_handler(Exception, handle_unexpected_error)

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        _: Request, error: RequestValidationError
    ) -> JSONResponse:
        """返回 FastAPI Schema 校验的稳定 422 错误。"""
        del error
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "INVALID_SCHEMA",
                    "category": "request",
                    "retryable": False,
                    "safe_message": "请求格式无效",
                }
            },
        )

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        """只报告进程存活和真实装配模式。"""
        return {"status": "ok", "mode": runtime_mode}

    async def readiness() -> dict[str, object] | JSONResponse:
        if dependency_probe is None:
            return {
                "status": "ok",
                "mode": runtime_mode,
                "dependencies": {"runtime_database": "not_configured"},
            }
        try:
            await dependency_probe()
        except RuntimeError:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "mode": runtime_mode,
                    "dependencies": {"runtime_database": "down"},
                },
            )
        return {
            "status": "ok",
            "mode": runtime_mode,
            "dependencies": {"runtime_database": "up"},
        }

    app.get("/health", response_model=None)(readiness)
    app.get("/health/ready", response_model=None)(readiness)

    return app


__all__ = ["create_app"]
