"""智能客服文档摄取内部接口契约测试。"""

from __future__ import annotations

import asyncio
from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest

from efficiency_platform_agent.agents.customer_service.ingest import (
    CustomerServiceIngestService,
)
from efficiency_platform_agent.agents.customer_service.ingest_repository import (
    InMemoryIngestJobRepository,
)
from efficiency_platform_agent.api.app import create_app

CONTENT = "# 公司制度\n\n请按流程提交审批。".encode()


class _Downloader:
    async def download(self, _url: str, _max_bytes: int) -> bytes:
        return CONTENT


class _Parser:
    def parse(self, content: bytes, _filename: str):
        return {"kind": "docling_markdown", "text": content.decode()}


class _Embedder:
    async def embed(self, texts):
        return tuple((0.01,) * 1024 for _ in texts)


class _Vectors:
    def __init__(self) -> None:
        self.writes = []

    async def replace_version_chunks(self, **values):
        self.writes.append(values)

    async def sync_and_verify_index_release(
        self, release_id, _knowledge_base_id, _documents
    ):
        return SimpleNamespace(
            release_id=release_id,
            document_count=2,
            chunk_count=3,
            checksum="b" * 64,
        )


def _service(content: bytes = CONTENT):
    downloader = _Downloader()
    if content != CONTENT:
        downloader.download = lambda *_: asyncio.sleep(0, result=content)
    return CustomerServiceIngestService(
        jobs=InMemoryIngestJobRepository(),
        downloader=downloader,
        parser=_Parser(),
        ocr=None,
        embedder=_Embedder(),
        vectors=_Vectors(),
    )


def _payload() -> dict[str, object]:
    return {
        "contract_version": "customer-service-ingest/1",
        "task_id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "dev",
        "knowledge_base_id": "22222222-2222-2222-2222-222222222222",
        "document_id": "33333333-3333-3333-3333-333333333333",
        "document_version_id": "44444444-4444-4444-4444-444444444444",
        "document_title": "公司制度",
        "version_no": 1,
        "file_name": "制度.md",
        "content_type": "text/markdown",
        "size_bytes": len(CONTENT),
        "sha256": sha256(CONTENT).hexdigest(),
        "download_url": "https://files.example.test/signed/document",
    }


@pytest.mark.asyncio
async def test_ingest_route_processes_document_and_is_idempotent() -> None:
    service = _service()
    app = create_app(
        SimpleNamespace(event_hub=None),  # type: ignore[arg-type]
        customer_service_ingest_service=service,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        accepted = await client.post(
            "/internal/v1/customer-service/ingest-jobs", json=_payload()
        )
        duplicate = await client.post(
            "/internal/v1/customer-service/ingest-jobs", json=_payload()
        )
        for _ in range(50):
            status = await client.get(
                "/internal/v1/customer-service/ingest-jobs/11111111-1111-1111-1111-111111111111"
            )
            if status.json()["status"] == "SUCCEEDED":
                break
            await asyncio.sleep(0)

    assert accepted.status_code == 202
    assert duplicate.status_code == 202
    assert status.json() == {
        "contract_version": "customer-service-ingest-view/1",
        "task_id": "11111111-1111-1111-1111-111111111111",
        "status": "SUCCEEDED",
        "stage": "VERIFY",
        "progress_percent": 100,
        "error_code": None,
        "error_message": None,
    }
    assert len(service.vectors.writes) == 1
    write = service.vectors.writes[0]
    assert len(write["parents"]) == 1
    assert write["parents"][0].content == "请按流程提交审批。"
    assert write["chunks"][0].parent_no == 1


@pytest.mark.asyncio
async def test_ingest_route_reports_oversized_indivisible_clause() -> None:
    content = ("# 公司制度\n\n第一条 " + "超长条款" * 700).encode()
    service = _service(content)
    app = create_app(
        SimpleNamespace(event_hub=None),  # type: ignore[arg-type]
        customer_service_ingest_service=service,
    )
    payload = _payload() | {
        "size_bytes": len(content),
        "sha256": sha256(content).hexdigest(),
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/internal/v1/customer-service/ingest-jobs", json=payload)
        for _ in range(50):
            status = await client.get(
                "/internal/v1/customer-service/ingest-jobs/11111111-1111-1111-1111-111111111111"
            )
            if status.json()["status"] == "FAILED":
                break
            await asyncio.sleep(0)
    assert status.json()["error_code"] == "KB_PARENT_CLAUSE_TOO_LONG"
    assert "完整条款" in status.json()["error_message"]


@pytest.mark.asyncio
async def test_ingest_route_rejects_extra_fields_and_reports_digest_failure() -> None:
    service = _service(b"tampered")
    app = create_app(
        SimpleNamespace(event_hub=None),  # type: ignore[arg-type]
        customer_service_ingest_service=service,
    )
    invalid = _payload() | {"unexpected": True}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        validation = await client.post(
            "/internal/v1/customer-service/ingest-jobs", json=invalid
        )
        await client.post("/internal/v1/customer-service/ingest-jobs", json=_payload())
        for _ in range(50):
            status = await client.get(
                "/internal/v1/customer-service/ingest-jobs/11111111-1111-1111-1111-111111111111"
            )
            if status.json()["status"] == "FAILED":
                break
            await asyncio.sleep(0)

    assert validation.status_code == 422
    assert status.json()["error_code"] == "KB_FILE_DIGEST_MISMATCH"
    assert status.json()["error_message"] == "文件完整性校验失败"


@pytest.mark.asyncio
async def test_index_verify_route_returns_stable_contract() -> None:
    service = _service()
    app = create_app(
        SimpleNamespace(event_hub=None),  # type: ignore[arg-type]
        customer_service_ingest_service=service,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/internal/v1/customer-service/index-releases/55555555-5555-5555-5555-555555555555/verify",
            json={
                "contract_version": "customer-service-index-verify/1",
                "release_id": "55555555-5555-5555-5555-555555555555",
                "knowledge_base_id": "22222222-2222-2222-2222-222222222222",
                "documents": [
                    {
                        "document_id": "33333333-3333-3333-3333-333333333333",
                        "document_version_id": "44444444-4444-4444-4444-444444444444",
                        "document_sha256": "a" * 64,
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["contract_version"] == "customer-service-index-verify-view/1"
    assert response.json()["status"] == "READY"
    assert response.json()["document_count"] == 2
