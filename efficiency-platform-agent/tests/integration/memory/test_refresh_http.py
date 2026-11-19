"""真实内部HTTP与双库刷新接合；Provider不发送，身份仅合成内部Bearer。"""

import json
from dataclasses import asdict, replace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy import text

from efficiency_platform_agent.api.memory_routes import build_memory_router
from efficiency_platform_agent.core.memory_refresh import (
    MemoryContextResume,
    ResumeMode,
    WaitPhase,
)
from efficiency_platform_agent.harness.hr_factory import internal_hr_authorizer
from efficiency_platform_agent.memory.context_refresh import MemoryContextRefreshService
from efficiency_platform_agent.persistence.memory_context_refresh import (
    MySqlMemoryContextRefreshStore,
)
from efficiency_platform_agent.security.memory_packet import memory_packet_digest
from tests.integration.context_control.test_memory_stop_http import running
from tests.integration.memory.test_refresh_persistence import (
    refresh_case as refresh_case,  # noqa: PLC0414 -- pytest共享真实隔离fixture。
)


@pytest.mark.parametrize("refresh_case", ["http-tenant"], indirect=True)
async def test_real_http_refresh_duplicate_historical_wait_and_original_budget(
    refresh_case,
):
    scope, record, store, registry, _ = refresh_case
    service = MemoryContextRefreshService(
        registry, MySqlMemoryContextRefreshStore(store)
    )
    wait_id = await service.begin_wait_intent(
        scope, record.runtime_id, "http-operation", 1, WaitPhase.BEFORE_PREPARE
    )
    await service.finish_wait(scope.conversation, scope.execution_id, wait_id)
    wait = await service.get_wait(scope.conversation, scope.execution_id)
    packet = replace(
        record.context.packet, packet_revision=2, issued_at=161, expires_at=190
    )
    refreshed = replace(
        record.context, packet=packet, packet_digest=memory_packet_digest(packet)
    )
    command = MemoryContextResume(
        wait_id,
        1,
        1,
        uuid4().hex,
        record.request_fingerprint,
        ResumeMode.REFRESH,
        False,
        "memory-context-resume/2",
        "http-operation",
        None,
        1,
        wait.expected_current_context_fingerprint,
        refreshed,
    )
    body = asdict(command)
    body["refreshed_context"] = {
        "schema_version": "memory-context/1",
        "memory_mode": "EXACT_ONLY",
        "scope": asdict(scope.conversation),
        "packet": asdict(packet),
        "authorization": {
            key: value for key, value in refreshed.metadata().items() if key != "packet"
        },
    }
    body = json.loads(
        json.dumps(
            body,
            default=lambda value: (
                sorted(value) if isinstance(value, (set, frozenset)) else str(value)
            ),
        )
    )
    secret = "synthetic-refresh-http-secret-32-bytes"
    headers = {
        "Authorization": "Bearer " + secret,
        "X-Tenant-ID": scope.conversation.tenant_id,
    }
    app = FastAPI()
    app.include_router(
        build_memory_router(
            store, internal_hr_authorizer(secret), None, refresh_service=service
        )
    )
    prefix = f"/internal/v1/memory/executions/{scope.execution_id}"
    async with running(app) as client:
        assert (await client.get(prefix + "/wait")).status_code == 401
        assert (
            await client.get(
                prefix + "/wait", headers=headers | {"X-Tenant-ID": "other"}
            )
        ).status_code == 404
        initial = await client.get(prefix + "/wait", headers=headers)
        assert initial.status_code == 200
        assert (
            initial.json()["expected_current_context_fingerprint"]
            == wait.expected_current_context_fingerprint
        )
        assert "value" not in initial.json()
        invalid = await client.post(
            prefix + "/resume", headers=headers, json=body | {"max_cost_cny": 1000}
        )
        assert invalid.status_code == 422
        resumed = await client.post(prefix + "/resume", headers=headers, json=body)
        assert resumed.status_code == 200, "真实刷新HTTP应返回结构化回执"
        assert resumed.json()["code"] == "CONTEXT_REFRESHED"
        assert resumed.json()["dispatch_allowed"] is False
        replay = await client.post(prefix + "/resume", headers=headers, json=body)
        assert replay.status_code == 200 and replay.json() == resumed.json()
        assert (await client.get(prefix + "/wait", headers=headers)).status_code == 404
        old_wait = await client.get(
            prefix + "/wait", params={"wait_event_id": wait_id}, headers=headers
        )
        assert (
            old_wait.status_code == 200
            and old_wait.json()["expected_current_context_fingerprint"]
            == wait.expected_current_context_fingerprint
        )
        assert old_wait.json()["logical_operation_id"] == "http-operation"
    current = await store.get(scope.conversation.tenant_id, scope.execution_id)
    assert (
        current.context == refreshed
        and current.request_fingerprint == record.request_fingerprint
    )
    assert current.deadline_epoch_seconds == record.deadline_epoch_seconds
    row = await registry._one(
        "SELECT refresh_count,state FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
        (scope.conversation.tenant_id, scope.execution_id),
    )
    assert row == {"refresh_count": 1, "state": "ACTIVE"}
    async with store.engine.connect() as connection:
        changed = (
            (
                await connection.execute(
                    text(
                        "SELECT context_fingerprint,current_context_fingerprint FROM agent_memory_execution WHERE tenant_id=:tenant AND execution_id=:execution"
                    ),
                    {
                        "tenant": scope.conversation.tenant_id.encode(),
                        "execution": scope.execution_id.encode(),
                    },
                )
            )
            .mappings()
            .one()
        )
    assert changed["context_fingerprint"] == wait.expected_current_context_fingerprint
    assert (
        changed["current_context_fingerprint"]
        == resumed.json()["current_context_fingerprint"]
    )
