"""FastAPI Run API 与有限 SSE 回放的契约测试。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from efficiency_platform_agent.contracts.events import RunEventV1
from efficiency_platform_agent.contracts.requests import (
    CancelRunRequestV1,
    CreateRunRequestV1,
    ResumeRunRequestV1,
)
from efficiency_platform_agent.contracts.responses import RunViewV1, UsageV1
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.harness.errors import HarnessError


def view(
    run_id: str = "run-1",
    *,
    status: RunStatus = RunStatus.SUCCEEDED,
    tenant: str = "tenant-1",
) -> RunViewV1:
    """构造不含敏感正文的最小公开视图。"""
    return RunViewV1(
        run_id=run_id,
        request_id="request-1",
        status=status,
        strategy=StrategyMode.DIRECT,
        output={"answer": "ok"} if status is RunStatus.SUCCEEDED else None,
        usage=UsageV1(
            input_tokens=1, output_tokens=1, cost_microunits=1, estimated=True
        ),
    )


@dataclass
class FakeService:
    """API 测试用的注入式服务，不触碰真实存储或网络。"""

    result: RunViewV1 = field(default_factory=view)
    events: list[RunEventV1] = field(default_factory=list)
    calls: list[tuple[str, Any]] = field(default_factory=list)
    error: HarnessError | None = None

    async def create_and_execute(self, request: CreateRunRequestV1) -> RunViewV1:
        self.calls.append(("create", request))
        if self.error:
            raise self.error
        return self.result

    async def get_run(self, run_id: str, tenant_id: str) -> RunViewV1:
        self.calls.append(("get", (run_id, tenant_id)))
        if self.error:
            raise self.error
        return self.result

    async def resume_run(self, run_id: str, request: ResumeRunRequestV1) -> RunViewV1:
        self.calls.append(("resume", (run_id, request)))
        if self.error:
            raise self.error
        return self.result

    async def cancel_run(self, run_id: str, request: CancelRunRequestV1) -> RunViewV1:
        self.calls.append(("cancel", (run_id, request)))
        if self.error:
            raise self.error
        return self.result

    async def list_events(
        self, run_id: str, tenant_id: str, after_sequence: int = 0
    ) -> tuple[RunEventV1, ...]:
        self.calls.append(("events", (run_id, tenant_id, after_sequence)))
        if self.error:
            raise self.error
        return tuple(event for event in self.events if event.sequence > after_sequence)


def client(service: FakeService) -> TestClient:
    """创建注入服务的测试客户端。"""
    from efficiency_platform_agent.api.app import create_app

    return TestClient(create_app(service))


def create_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "request_id": "request-1",
        "tenant_id": "tenant-1",
        "user_id": "user-1",
        "input_text": "hello",
        "requested_strategy": "direct",
    }
    body.update(overrides)
    return body


def test_create_run_returns_201_and_forwards_tenant() -> None:
    service = FakeService()
    response = client(service).post(
        "/v1/runs", json=create_body(), headers={"X-Tenant-ID": "tenant-1"}
    )
    assert response.status_code == 201
    assert response.json()["run_id"] == "run-1"
    assert service.calls[0][0] == "create"


def test_create_app_registers_injected_upload_service() -> None:
    from efficiency_platform_agent.api.app import create_app

    class FakeDocumentService:
        async def ingest(self, content, filename, mime_type, upload_id):
            assert content == "正文".encode()
            assert filename == "note.md"
            assert mime_type == "text/markdown"
            assert upload_id == "run-1:tenant-1:note.md"
            return SimpleNamespace(
                quality_status="accepted",
                reason_codes=(),
                chunk_ids=("chunk-1",),
                artifact_reference="artifact-1",
            )

    app = create_app(FakeService(), document_service=FakeDocumentService())
    response = TestClient(app).post(
        "/v1/runs/run-1/files",
        files={"file": ("note.md", "正文".encode(), "text/markdown")},
        headers={"X-Tenant-ID": "tenant-1"},
    )

    assert response.status_code == 200
    assert response.json()["artifact_reference"] == "artifact-1"


def test_schema_extra_and_tenant_mismatch_are_rejected() -> None:
    service = FakeService()
    extra = client(service).post(
        "/v1/runs", json=create_body(unknown="x"), headers={"X-Tenant-ID": "tenant-1"}
    )
    mismatch = client(service).post(
        "/v1/runs", json=create_body(), headers={"X-Tenant-ID": "tenant-2"}
    )
    assert extra.status_code == 422
    assert mismatch.status_code == 403


def test_get_cross_tenant_is_not_found() -> None:
    service = FakeService(
        error=HarnessError("RUN_NOT_FOUND", "Run 不存在", category="request")
    )
    response = client(service).get(
        "/v1/runs/run-1", headers={"X-Tenant-ID": "tenant-2"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_resume_and_cancel_statuses_are_stable() -> None:
    service = FakeService(result=view(status=RunStatus.WAITING_INPUT))
    c = client(service)
    resume = c.post(
        "/v1/runs/run-1/resume",
        json={
            "tenant_id": "tenant-1",
            "checkpoint_id": "cp-1",
            "resume_value": {"answer": "ok"},
        },
        headers={"X-Tenant-ID": "tenant-1"},
    )
    cancel = c.post(
        "/v1/runs/run-1/cancel",
        json={"tenant_id": "tenant-1", "reason_code": "user_requested"},
        headers={"X-Tenant-ID": "tenant-1"},
    )
    assert resume.status_code == 200
    assert cancel.status_code == 200


def test_error_mapping_and_health_are_safe() -> None:
    service = FakeService(
        error=HarnessError("RUN_NOT_WAITING_INPUT", "Run 当前不等待补充输入")
    )
    response = client(service).post(
        "/v1/runs/run-1/resume",
        json={
            "tenant_id": "tenant-1",
            "checkpoint_id": "cp-1",
            "resume_value": {"secret": "do-not-leak"},
        },
        headers={"X-Tenant-ID": "tenant-1"},
    )
    health = client(FakeService()).get("/health/live")
    assert response.status_code == 409
    assert "do-not-leak" not in response.text
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "mode": "s2_fake_in_memory"}


def test_sse_serializes_events_and_replays_after_last_event_id() -> None:
    events = [
        RunEventV1(
            event_id="e-1",
            event_type="run_started",
            run_id="run-1",
            sequence=1,
            occurred_at_epoch_ms=1,
            status=RunStatus.RUNNING,
        ),
        RunEventV1(
            event_id="e-2",
            event_type="run_succeeded",
            run_id="run-1",
            sequence=2,
            occurred_at_epoch_ms=2,
            status=RunStatus.SUCCEEDED,
        ),
    ]
    service = FakeService(events=events)
    c = client(service)
    first = c.get("/v1/runs/run-1/events", headers={"X-Tenant-ID": "tenant-1"})
    second = c.get(
        "/v1/runs/run-1/events",
        headers={"X-Tenant-ID": "tenant-1", "Last-Event-ID": "1"},
    )
    assert first.status_code == second.status_code == 200
    assert "id: 1" in first.text and "event: run_started" in first.text
    assert "id: 1" not in second.text and "id: 2" in second.text
    assert (
        json.loads(
            next(
                line[6:]
                for line in second.text.splitlines()
                if line.startswith("data: ")
            )
        )["event_id"]
        == "e-2"
    )


def test_sse_rejects_invalid_cursor() -> None:
    response = client(FakeService()).get(
        "/v1/runs/run-1/events",
        headers={"X-Tenant-ID": "tenant-1", "Last-Event-ID": "nope"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_EVENT_CURSOR"
    empty = client(FakeService()).get(
        "/v1/runs/run-1/events",
        headers={"X-Tenant-ID": "tenant-1", "Last-Event-ID": ""},
    )
    assert empty.status_code == 400


def test_sse_cross_tenant_error_is_mapped_before_streaming() -> None:
    service = FakeService(
        error=HarnessError("RUN_NOT_FOUND", "Run 不存在", category="request")
    )
    response = client(service).get(
        "/v1/runs/run-1/events", headers={"X-Tenant-ID": "tenant-2"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RUN_NOT_FOUND"
