"""内部cleanup路由的拒绝边界；单元替身不作真实清理验收证据。"""

from dataclasses import asdict, replace
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from efficiency_platform_agent.api.memory_routes import build_memory_router
from tests.integration.context_control.test_memory_execution_mysql import context


@pytest.mark.asyncio
@pytest.mark.parametrize("pending", [False, True])
async def test_cleanup_persists_revocation_then_waits_actual_stop_and_never_invents_other_targets(
    pending,
):
    original = context()
    original = replace(
        original,
        packet=replace(
            original.packet, scope=replace(original.packet.scope, tenant_id="tenant")
        ),
    )
    order = []

    class Store:
        async def invalidate(self, event):
            order.append("revoke")
            return "memory-stop-" + "a" * 32

        async def get(self, tenant, execution):
            return SimpleNamespace(context=original, state="REVOKED")

    async def authorize(request):
        return original.packet.scope.tenant_id

    async def stop(record):
        assert order == ["revoke"]
        order.append("stop")
        if pending:
            raise ValueError("MEMORY_STOP_PENDING")

    app = FastAPI()
    app.include_router(build_memory_router(Store(), authorize, stop))
    body = {
        "event_id": "event",
        "expected_execution_revision": 1,
        "grant_epoch": 1,
        "source_epoch": 1,
        "deletion_epoch": 1,
        "source_dependencies": [
            asdict(dep) for dep in original.packet.safety_dependencies
        ],
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/internal/v1/memory/executions/{original.packet.execution_id}/cleanup",
            headers={"X-Tenant-ID": original.packet.scope.tenant_id},
            json=body,
        )
    assert response.status_code == (503 if pending else 200)
    if not pending:
        assert response.json()["receipts"] == {"AGENT_STOP": "memory-stop-" + "a" * 32}
    assert order == ["revoke", "stop"]


@pytest.mark.asyncio
async def test_public_body_cannot_supply_a_cleanup_receipt():
    from unittest.mock import AsyncMock

    store = AsyncMock()

    async def authorize(request):
        return "tenant"

    app = FastAPI()
    app.include_router(build_memory_router(store, authorize, AsyncMock()))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/internal/v1/memory/executions/execution/cleanup",
            headers={"X-Tenant-ID": "tenant"}, json={"event_id": "event", "expected_execution_revision": 1,
            "grant_epoch": 1, "source_epoch": 1, "deletion_epoch": 1, "source_dependencies": [],
            "receipts": {"THREADS": "forged-client-receipt"}})
    assert response.status_code == 422
    store.invalidate.assert_not_awaited()
    store.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_durable_full_cleanup_receipt_replays_without_decrypting_or_stopping_again():
    from unittest.mock import AsyncMock

    store, stop, journal = AsyncMock(), AsyncMock(), AsyncMock()
    journal.receipts.return_value = {"AGENT_STOP": "original-stop", "THREADS": "original-threads", "SNAPSHOT": "original-scrub"}

    async def authorize(request):
        return "tenant"

    original = context()
    app = FastAPI()
    app.include_router(build_memory_router(store, authorize, stop, cleanup_journal=journal))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/internal/v1/memory/executions/execution/cleanup", headers={"X-Tenant-ID": "tenant"},
            json={"event_id": "event", "expected_execution_revision": 1, "grant_epoch": 1, "source_epoch": 1,
            "deletion_epoch": 1, "source_dependencies": [asdict(dep) for dep in original.packet.safety_dependencies]})
    assert response.status_code == 200 and response.json()["receipts"] == journal.receipts.return_value
    store.get.assert_not_awaited()
    stop.assert_not_awaited()
