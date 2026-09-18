"""真实验收内部 API 默认不挂载、显式注入后才可调用。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from efficiency_platform_agent.api.app import create_app
from efficiency_platform_agent.core.budget_lease import BudgetCharge
from efficiency_platform_agent.harness.live_acceptance import (
    InMemoryLiveAcceptanceAuthorizationStore,
    InMemoryLiveAcceptanceBudgetBinder,
    LiveAcceptanceAuthorization,
    LiveAcceptanceService,
)

NOW = datetime(2026, 9, 17, 8, tzinfo=UTC)


class _Runner:
    async def run_case(self, case_id, prompt, binding):
        reservation = await binding.port.reserve(
            binding.scope,
            f"case:{case_id}",
            BudgetCharge(calls=1, cost_microunits=10),
            (await binding.port.snapshot(binding.scope)).version,
        )
        await binding.port.mark_dispatched(reservation.reservation_id)
        await binding.port.settle(
            reservation.reservation_id,
            BudgetCharge(calls=1, cost_microunits=10),
            "success",
        )
        return {
            "case_id": case_id,
            "status": "PASS",
            "run_id": f"run-{case_id}",
            "real_model_verified": True,
            "real_source_verified": True,
        }


def _service() -> LiveAcceptanceService:
    authorization = LiveAcceptanceAuthorization(
        authorization_id="approval-1",
        approved_by="project-owner",
        approved_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=30),
        allowed_actions=frozenset({"model_evaluation", "source_read"}),
        allowed_case_ids=("yesterday_ai",),
        allowed_tenant_ids=("tenant-acceptance",),
        max_budget_microunits=20,
    )
    return LiveAcceptanceService(
        authorizations=InMemoryLiveAcceptanceAuthorizationStore((authorization,)),
        budget_binder=InMemoryLiveAcceptanceBudgetBinder(
            clock_ms=lambda: int(NOW.timestamp() * 1_000)
        ),
        runner=_Runner(),
        now=lambda: NOW,
    )


@pytest.mark.asyncio
async def test_internal_acceptance_route_requires_explicit_service_injection() -> None:
    runtime = SimpleNamespace(event_hub=None)
    unbound = create_app(runtime)  # type: ignore[arg-type]
    bound = create_app(  # type: ignore[arg-type]
        runtime,
        live_acceptance_service=_service(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=unbound), base_url="http://test"
    ) as client:
        assert (
            await client.post(
                "/v1/internal/research-v2/live-acceptance",
                headers={"X-Tenant-ID": "tenant-acceptance"},
                json={
                    "request_id": "acceptance-1",
                    "authorization_id": "approval-1",
                    "case_ids": ["yesterday_ai"],
                    "requested_budget_microunits": 20,
                },
            )
        ).status_code == 404

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=bound), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/internal/research-v2/live-acceptance",
            headers={"X-Tenant-ID": "tenant-acceptance"},
            json={
                "request_id": "acceptance-1",
                "authorization_id": "approval-1",
                "case_ids": ["yesterday_ai"],
                "requested_budget_microunits": 20,
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "PASS"
    assert response.json()["used_cost_microunits"] == 10


@pytest.mark.asyncio
async def test_internal_acceptance_route_rejects_unapproved_tenant() -> None:
    app = create_app(  # type: ignore[arg-type]
        SimpleNamespace(event_hub=None),
        live_acceptance_service=_service(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/internal/research-v2/live-acceptance",
            headers={"X-Tenant-ID": "tenant-other"},
            json={
                "request_id": "acceptance-1",
                "authorization_id": "approval-1",
                "case_ids": ["yesterday_ai"],
                "requested_budget_microunits": 20,
            },
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
