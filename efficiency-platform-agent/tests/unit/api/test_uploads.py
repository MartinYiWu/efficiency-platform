"""运行文件上传路由的离线边界测试。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from efficiency_platform_agent.api.uploads import build_upload_router
from efficiency_platform_agent.capabilities.document.contracts import (
    DocumentIngestionResult,
    DocumentQualityStatus,
)


class _FakeService:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str, str, str]] = []

    async def ingest(
        self, content: bytes, filename: str, mime_type: str, upload_id: str
    ) -> DocumentIngestionResult:
        self.calls.append((content, filename, mime_type, upload_id))
        return DocumentIngestionResult(
            {"kind": "synthetic"}, DocumentQualityStatus.ACCEPTED, (), ("c1",), "a1"
        )


def _client(service: _FakeService) -> TestClient:
    app = FastAPI()
    app.include_router(build_upload_router(service))
    return TestClient(app)


def test_upload_route_binds_run_and_tenant_context():
    service = _FakeService()
    response = _client(service).post(
        "/v1/runs/run-1/files",
        headers={"X-Tenant-ID": "tenant-1"},
        files={"file": ("note.md", b"hello", "text/markdown")},
    )
    assert response.status_code == 200
    assert response.json()["run_id"] == "run-1"
    assert response.json()["tenant_id"] == "tenant-1"
    assert service.calls == [
        (b"hello", "note.md", "text/markdown", "run-1:tenant-1:note.md")
    ]


def test_upload_route_rejects_invalid_scope_before_service_call():
    service = _FakeService()
    response = _client(service).post(
        "/v1/runs/run-1/files",
        headers={"X-Tenant-ID": "tenant/id"},
        files={"file": ("note.md", b"hello", "text/markdown")},
    )
    assert response.status_code == 400
    assert service.calls == []
