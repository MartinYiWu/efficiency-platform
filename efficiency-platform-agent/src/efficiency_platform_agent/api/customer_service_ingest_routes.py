"""智能客服文档摄取和候选索引验证内部路由。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from efficiency_platform_agent.capabilities.customer_service_ingest import (
    CustomerServiceIngestPort,
    IndexVerifyRequest,
    IndexVerifyView,
    IngestJobRequest,
    IngestJobView,
)


def build_customer_service_ingest_router(
    service: CustomerServiceIngestPort,
) -> APIRouter:
    router = APIRouter(prefix="/internal/v1/customer-service")

    @router.post(
        "/ingest-jobs",
        response_model=IngestJobView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def submit_ingest(request: IngestJobRequest) -> IngestJobView:
        return await service.submit(request)

    @router.get("/ingest-jobs/{task_id}", response_model=IngestJobView)
    async def get_ingest(task_id: UUID) -> IngestJobView:
        value = await service.get(task_id)
        if value is None:
            raise HTTPException(status_code=404, detail="摄取任务不存在")
        return value

    @router.post("/index-releases/{release_id}/verify", response_model=IndexVerifyView)
    async def verify_index(
        release_id: UUID, request: IndexVerifyRequest
    ) -> IndexVerifyView:
        if request.release_id != release_id:
            raise HTTPException(status_code=422, detail="索引版本不一致")
        try:
            result = await service.verify_index(release_id)
            return IndexVerifyView(
                release_id=release_id,
                status="READY",
                document_count=result.document_count,
                chunk_count=result.chunk_count,
                checksum=result.checksum,
            )
        except RuntimeError as error:
            if getattr(error, "code", None) != "KB_INDEX_VERIFY_FAILED":
                raise
            return IndexVerifyView(
                release_id=release_id,
                status="FAILED",
                document_count=0,
                chunk_count=0,
                error_code="KB_INDEX_VERIFY_FAILED",
                error_message="候选索引验证失败",
            )

    return router


__all__ = ["build_customer_service_ingest_router"]
