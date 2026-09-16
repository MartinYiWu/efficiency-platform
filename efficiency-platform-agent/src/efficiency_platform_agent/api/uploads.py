"""上传 API 薄接线；实际摄取由 DocumentIngestionService 注入。"""

from __future__ import annotations

import re

from fastapi import APIRouter, Header, HTTPException, UploadFile

from ..capabilities.document.service import DocumentIngestionService

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_SCOPE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


def build_upload_router(service: DocumentIngestionService) -> APIRouter:
    """构造带运行和租户边界的 multipart 上传路由。"""
    router = APIRouter(prefix="/v1")

    @router.post("/runs/{run_id}/files")
    async def upload(
        run_id: str,
        file: UploadFile,
        tenant_id: str = Header(..., alias="X-Tenant-ID"),
    ):
        if (
            _SCOPE_ID.fullmatch(run_id) is None
            or _SCOPE_ID.fullmatch(tenant_id) is None
        ):
            raise HTTPException(status_code=400, detail="运行或租户标识无效")
        content = await file.read(_MAX_UPLOAD_BYTES + 1)
        if len(content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="文件超过大小上限")
        filename = file.filename or ""
        result = await service.ingest(
            content,
            filename,
            file.content_type or "",
            f"{run_id}:{tenant_id}:{filename}",
        )
        return {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "quality_status": result.quality_status,
            "reason_codes": result.reason_codes,
            "chunk_ids": result.chunk_ids,
            "artifact_reference": result.artifact_reference,
        }

    return router


__all__ = ["build_upload_router"]
