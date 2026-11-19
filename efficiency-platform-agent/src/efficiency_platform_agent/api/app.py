"""FastAPI 应用工厂；不在导入时创建运行时全局实例。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from efficiency_platform_agent.core.memory_cleanup import MemoryCleanupJournal
from efficiency_platform_agent.core.memory_execution import MemoryExecutionStore
from efficiency_platform_agent.harness.errors import HarnessError

from .routes import build_router, handle_harness_error, handle_unexpected_error
from .uploads import build_upload_router

if TYPE_CHECKING:
    from efficiency_platform_agent.agents.customer_service.service import (
        CustomerServiceRunService,
    )
    from efficiency_platform_agent.capabilities.customer_service_ingest import (
        CustomerServiceIngestPort,
    )
    from efficiency_platform_agent.capabilities.document.service import (
        DocumentIngestionService,
    )
    from efficiency_platform_agent.capabilities.model.memory_derive_handler import (
        MemoryDeriveHandler,
    )
    from efficiency_platform_agent.conversation.service import ConversationService
    from efficiency_platform_agent.harness.live_acceptance import (
        LiveAcceptanceService,
    )
    from efficiency_platform_agent.harness.service import AgentRuntimeService
    from efficiency_platform_agent.runtime.event_hub import EventHub

    from .hr_skill_routes import HrSkillEndpoint


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
    hr_skill_endpoint: object | None = None,
    hr_skill_authorizer: Callable[[Request], Awaitable[str]] | None = None,
    context_internal_authorizer: Callable[[Request], Awaitable[str]] | None = None,
    memory_enabled: bool = False,
    memory_execution_store: MemoryExecutionStore | None = None,
    memory_manifest_reader: Callable | None = None,
    memory_erase_threads: Callable | None = None,
    memory_cleanup_journal: MemoryCleanupJournal | None = None,
    memory_resume_execution: Callable | None = None,
    memory_refresh_service=None,
    memory_derive_coordinator=None,
    memory_derive_endpoint: MemoryDeriveHandler | None = None,
    memory_index_runtime=None,
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
    if memory_index_runtime is not None:
        from efficiency_platform_agent.harness.memory_index_runtime import (
            MemoryIndexCleanupRuntime,
        )

        if context_internal_authorizer is None or (
            not memory_enabled
            and type(memory_index_runtime) is not MemoryIndexCleanupRuntime
        ):
            raise ValueError("MEMORY_INDEX_AUTHORITY_REQUIRED")
        from .memory_index_routes import build_memory_index_router

        app.include_router(
            build_memory_index_router(memory_index_runtime, context_internal_authorizer)
        )
        app.router.add_event_handler(
            "startup", memory_index_runtime.expiry_worker.start
        )
        app.router.add_event_handler(
            "shutdown", memory_index_runtime.expiry_worker.close
        )
    if memory_enabled:
        from efficiency_platform_agent.core.memory_execution import (
            MemoryExecutionRecord,
        )

        from .memory_routes import build_memory_router

        if memory_execution_store is None or context_internal_authorizer is None:
            raise ValueError("MEMORY_AUTHORITY_REQUIRED")
        if memory_cleanup_journal is not None:

            async def scrub_memory_runtime(record: MemoryExecutionRecord) -> bool:
                if (
                    record.runtime_kind == "CUSTOMER_SERVICE"
                    and customer_service_run_service is not None
                ):
                    return await cast(
                        "CustomerServiceRunService", customer_service_run_service
                    ).scrub_memory_execution(record)
                if record.runtime_kind == "OPERATIONS":
                    if not await service.scrub_memory_execution(record):
                        return False
                    return (
                        conversation_service is not None
                        and await conversation_service.scrub_memory_execution(record)
                    )
                return False

            memory_cleanup_journal.runtime_scrubber = scrub_memory_runtime

        async def stop_memory_execution(record: MemoryExecutionRecord) -> None:
            tenant = record.context.packet.scope.tenant_id
            if record.runtime_kind == "OPERATIONS":
                await service.stop_memory_execution(record.runtime_id, tenant)
            elif (
                record.runtime_kind == "CUSTOMER_SERVICE"
                and customer_service_run_service is not None
            ):
                from uuid import UUID

                await cast(
                    "CustomerServiceRunService", customer_service_run_service
                ).stop_memory_execution(UUID(record.runtime_id))  # type: ignore[attr-defined]
            elif record.runtime_kind == "HR" and hr_skill_endpoint is not None:
                await hr_skill_endpoint.cancel(tenant, record.context.packet.task_id)  # type: ignore[attr-defined]
                raise ValueError("MEMORY_STOP_PENDING")
            else:
                raise ValueError("MEMORY_STOP_ADAPTER_REQUIRED")

        app.include_router(
            build_memory_router(
                memory_execution_store,
                context_internal_authorizer,
                stop_memory_execution,
                memory_manifest_reader,
                memory_erase_threads,
                memory_cleanup_journal,
                memory_resume_execution,
                refresh_service=memory_refresh_service,
                memory_derive_coordinator=memory_derive_coordinator,
            )
        )
    from .hr_skill_routes import build_hr_skill_router

    app.include_router(
        build_hr_skill_router(
            cast("HrSkillEndpoint | None", hr_skill_endpoint),
            hr_skill_authorizer,
            memory_enabled=memory_enabled,  # type: ignore[arg-type]
            memory_derive_endpoint=memory_derive_endpoint,
            memory_derive_authorize=context_internal_authorizer,
        )  # type: ignore[arg-type]
    )
    resolved_event_hub = event_hub or getattr(service, "event_hub", None)
    app.state.event_hub = resolved_event_hub
    app.include_router(build_router(service, resolved_event_hub))
    if conversation_service is not None:
        from .conversation_routes import build_conversation_router

        app.state.conversation_service = conversation_service
        app.include_router(
            build_conversation_router(
                conversation_service,
                context_internal_authorizer,
                memory_enabled=memory_enabled,
            )
        )
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
            build_customer_service_router(
                customer_service_run_service,  # type: ignore[arg-type]
                context_internal_authorizer,
                memory_enabled=memory_enabled,
            )
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
