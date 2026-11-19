"""R04真实内部HTTP拒绝矩阵，所有非法请求必须在两库计数变化前失败。"""

import copy
import json
import os
from dataclasses import asdict

import pytest
from fastapi import FastAPI
from sqlalchemy import text

from efficiency_platform_agent.api.memory_routes import build_memory_router
from efficiency_platform_agent.harness.hr_factory import internal_hr_authorizer
from tests.integration.context_control.test_memory_stop_http import running
from tests.integration.memory.test_refresh_persistence import (
    _begin_refresh_candidate,
)
from tests.integration.memory.test_refresh_persistence import (
    refresh_case as refresh_case,  # noqa: PLC0414
)

pytestmark = pytest.mark.skipif(
    os.environ.get("MEMORY_IT_ENABLED") != "1", reason="需root本机隔离双库"
)


@pytest.mark.parametrize("refresh_case", ["http-negative-tenant"], indirect=True)
async def test_real_refresh_http_rejects_changed_bindings_without_counting(
    refresh_case,
):
    scope, original, store, registry, _ = refresh_case
    service, wait, command = await _begin_refresh_candidate(refresh_case)
    context = command.refreshed_context
    body = asdict(command)
    body["refreshed_context"] = {
        "schema_version": "memory-context/1",
        "memory_mode": "EXACT_ONLY",
        "scope": asdict(scope.conversation),
        "packet": asdict(context.packet),
        "authorization": {
            key: value for key, value in context.metadata().items() if key != "packet"
        },
    }
    body = json.loads(json.dumps(body, default=lambda value: sorted(value)))
    secret = "synthetic-rf07-rejection-internal-secret-32"
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
        assert (await client.post(prefix + "/resume", json=body)).status_code == 401
        assert (
            await client.post(
                prefix + "/resume",
                headers=headers | {"X-Tenant-ID": "other-tenant"},
                json=body,
            )
        ).status_code == 404
        changes = (
            ("wait_event_id", "another-wait", 409),
            ("packet_revision", 2, 422),
            ("expected_execution_revision", 2, 422),
            ("operation_hash", "f" * 64, 409),
            ("logical_operation_id", "another-operation", 409),
            ("attempt", 2, 409),
            ("expected_current_context_fingerprint", "f" * 64, 409),
            ("new_content", True, 422),
            ("attempt", True, 422),
            ("max_cost_cny", 1000, 422),
        )
        for key, value, expected in changes:
            response = await client.post(
                prefix + "/resume", headers=headers, json=body | {key: value}
            )
            assert response.status_code == expected, key
            current = await store.get(scope.conversation.tenant_id, scope.execution_id)
            assert current == original
            row = await registry._one(
                "SELECT state,refresh_count,pending_resume_request_id FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
                (scope.conversation.tenant_id, scope.execution_id),
            )
            assert row == {
                "state": "WAITING_CONTEXT",
                "refresh_count": 0,
                "pending_resume_request_id": None,
            }
            async with store.engine.connect() as connection:
                count = (
                    await connection.execute(
                        text(
                            "SELECT COUNT(*) FROM agent_memory_context_refresh WHERE tenant_id=:tenant AND execution_id=:execution AND record_kind='REFRESH'"
                        ),
                        {
                            "tenant": scope.conversation.tenant_id.encode(),
                            "execution": scope.execution_id.encode(),
                        },
                    )
                ).scalar_one()
                assert count == 0
        accepted = await client.post(prefix + "/resume", headers=headers, json=body)
        assert accepted.status_code == 200
        assert accepted.json()["refresh_count"] == 1
        for _ in range(3):
            replay = await client.post(prefix + "/resume", headers=headers, json=body)
            assert replay.json() == accepted.json()
        changed = copy.deepcopy(body)
        changed["refreshed_context"]["packet"]["expires_at"] += 1
        conflict = await client.post(prefix + "/resume", headers=headers, json=changed)
        assert conflict.status_code in (409, 422)
    assert (
        await service.get_wait(
            scope.conversation, scope.execution_id, wait.wait_event_id
        )
    ).expected_current_context_fingerprint == wait.expected_current_context_fingerprint
    row = await registry._one(
        "SELECT refresh_count FROM {execution} WHERE tenant_id=%s AND execution_id=%s",
        (scope.conversation.tenant_id, scope.execution_id),
    )
    assert row["refresh_count"] == 1
