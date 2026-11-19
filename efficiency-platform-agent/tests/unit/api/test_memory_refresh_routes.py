"""刷新HTTP协议单元边界；真实持久状态机另用隔离双库验收。"""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from efficiency_platform_agent.api.memory_routes import build_memory_router
from efficiency_platform_agent.contracts.memory_refresh import (
    MemoryContextResumeModel,
    MemoryContextResumeReceiptModel,
    MemoryContextWaitModel,
)
from tests.unit.persistence.test_context_manifest import setup as setup  # noqa: PLC0414


def golden():
    raw = (
        Path(__file__).parents[2] / "fixtures/memory_refresh_transport.json"
    ).read_text(encoding="utf-8")
    tenant = json.loads(raw)["wait"]["scope"]["tenant_id"]
    return json.loads(raw.replace(tenant, "tenant-api"))


def test_refresh_flag_defaults_off_and_requires_memory_authority():
    from pydantic import ValidationError

    from efficiency_platform_agent.configuration.integration import (
        S7IntegrationSettings,
    )

    assert S7IntegrationSettings().memory_refresh_enabled is False
    with pytest.raises(ValidationError, match="MEMORY_REFRESH_REQUIRES_MEMORY"):
        S7IntegrationSettings(memory_refresh_enabled=True)


def test_internal_wait_event_contains_only_opaque_reference():
    from pydantic import ValidationError

    from efficiency_platform_agent.contracts.stream_events import RunStreamEventV1

    event = RunStreamEventV1(
        event="context_refresh_required",
        run_id="run",
        sequence=1,
        payload={"wait_event_id": "opaque-wait"},
    )
    assert event.payload == {"wait_event_id": "opaque-wait"}
    with pytest.raises(ValidationError):
        RunStreamEventV1(
            event="context_refresh_required",
            run_id="run",
            sequence=1,
            payload={"wait_event_id": "opaque-wait", "prompt": "synthetic"},
        )


async def test_disabled_refresh_query_returns_capability_error_without_loading_body():
    async def authorize(request):
        return "tenant"

    class Store:
        async def get(self, *args):
            pytest.fail("缺端口不应读取快照")

    app = FastAPI()
    app.include_router(build_memory_router(Store(), authorize, None))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/internal/v1/memory/executions/e/wait", headers={"X-Tenant-ID": "tenant"}
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "MEMORY_REFRESH_CAPABILITY_UNSUPPORTED"


@pytest.mark.parametrize("state", ["ACTIVE", "REVOKED"])
async def test_authenticated_wait_and_resume_use_server_scope_and_full_receipt(state):
    sample = golden()
    wait = MemoryContextWaitModel.model_validate_json(
        json.dumps(sample["wait"])
    ).to_core()
    command = MemoryContextResumeModel.model_validate_json(
        json.dumps(sample["resume"])
    ).to_core()
    response = MemoryContextResumeReceiptModel.model_validate_json(
        json.dumps(sample["receipt"])
    ).to_core()
    calls = []

    class Store:
        async def get(self, tenant, execution):
            assert (tenant, execution) == (wait.scope.tenant_id, wait.execution_id)
            return SimpleNamespace(
                context=SimpleNamespace(packet=SimpleNamespace(scope=wait.scope)),
                state=state,
                runtime_id=wait.runtime_id,
            )

    class Refresh:
        async def get_wait(self, scope, execution):
            calls.append("wait")
            assert scope == wait.scope and execution == wait.execution_id
            return wait

        async def resume(self, scope, execution, candidate):
            calls.append("resume")
            assert (
                scope == wait.scope
                and execution == wait.execution_id
                and candidate == command
            )
            return response

    async def authorize(request):
        if request.headers.get("Authorization") != "Bearer synthetic-internal":
            raise PermissionError
        return wait.scope.tenant_id

    app = FastAPI()
    app.include_router(
        build_memory_router(Store(), authorize, None, refresh_service=Refresh())
    )
    prefix = f"/internal/v1/memory/executions/{wait.execution_id}"
    headers = {
        "Authorization": "Bearer synthetic-internal",
        "X-Tenant-ID": wait.scope.tenant_id,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get(prefix + "/wait")).status_code == 401
        assert (
            await client.get(
                prefix + "/wait", headers=headers | {"X-Tenant-ID": "other"}
            )
        ).status_code == 403
        got = await client.get(prefix + "/wait", headers=headers)
        posted = await client.post(
            prefix + "/resume", headers=headers, json=sample["resume"]
        )
        invalid = await client.post(
            prefix + "/resume",
            headers=headers,
            json=sample["resume"] | {"max_cost_cny": 999},
        )
    assert invalid.status_code == 422
    assert got.status_code == posted.status_code == (200 if state == "ACTIVE" else 409)
    if state == "ACTIVE":
        assert got.json() == sample["wait"]
        assert posted.json() == sample["receipt"]
        assert calls == ["wait", "resume"]
    else:
        assert calls == []


async def test_unknown_refresh_error_does_not_echo_driver_or_body():
    sample = golden()
    wait = MemoryContextWaitModel.model_validate_json(
        json.dumps(sample["wait"])
    ).to_core()

    class Store:
        async def get(self, tenant, execution):
            return SimpleNamespace(
                context=SimpleNamespace(packet=SimpleNamespace(scope=wait.scope)),
                state="ACTIVE",
                runtime_id=wait.runtime_id,
            )

    class Refresh:
        async def get_wait(self, *args):
            raise ValueError("synthetic-driver-private-details")

    async def authorize(request):
        return wait.scope.tenant_id

    app = FastAPI()
    app.include_router(
        build_memory_router(Store(), authorize, None, refresh_service=Refresh())
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        result = await client.get(
            f"/internal/v1/memory/executions/{wait.execution_id}/wait",
            headers={"X-Tenant-ID": wait.scope.tenant_id},
        )
    assert result.status_code == 503
    assert result.json() == {"detail": "MEMORY_AUTHORITY_UNAVAILABLE"}


@pytest.mark.parametrize(
    "enabled,approved,revision,expected",
    (
        (True, True, 1, 200),
        (True, False, 1, 409),
        (False, True, 1, 409),
        (True, False, 2, 409),
    ),
)
async def test_manifest_history_requires_actual_execution_audit(
    setup, enabled, approved, revision, expected
):
    manifest = replace(
        setup["prepared"].manifest, packet_id="packet", packet_revision=revision
    )
    scope = manifest.scope.conversation
    record = SimpleNamespace(
        context=SimpleNamespace(
            packet=SimpleNamespace(scope=scope, packet_id="packet", packet_revision=2)
        ),
        runtime_id="runtime",
        state="ACTIVE",
    )
    audited = []

    class Store:
        async def get(self, tenant, execution):
            return record

    class Refresh:
        async def validate_execution_manifest(self, item, current):
            assert item is manifest and current is record
            audited.append(item)
            return approved

    async def authorize(request):
        return scope.tenant_id

    async def manifests(tenant, execution):
        return (manifest,)

    app = FastAPI()
    app.include_router(
        build_memory_router(
            Store(),
            authorize,
            None,
            manifests=manifests,
            refresh_service=Refresh() if enabled else None,
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/internal/v1/memory/executions/{manifest.scope.execution_id}/manifest",
            headers={"X-Tenant-ID": scope.tenant_id},
        )
    assert response.status_code == expected
    if expected == 200:
        assert response.json()["packet_revision"] == 2
        assert response.json()["manifests"][0]["packet_revision"] == 1
    if enabled:
        assert audited == [manifest]
