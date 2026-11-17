"""两租户两用户的客服会话/HR TASK_ONLY真实HTTP矩阵，供应商仅Fake。"""

from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.integration.context_control.business_http_fixture import (
    RELEASE,
    SECRET,
    running_business_app,
    seed_hr_run,
)


def memory_context(tenant, user, agent, session=None):
    return {
        "schema_version": "memory-context/1",
        "memory_mode": "DISABLED",
        "packet": None,
        "scope": {
            "tenant_id": tenant,
            "user_id": user,
            "domain": agent,
            "top_level_agent_id": agent,
            "session_kind": "TASK_ONLY" if agent == "hr" else "CONVERSATION",
            "session_id": session,
        },
    }


def customer_body(tenant, user, session, request_id):
    return {
        "contract_version": "customer-service-run/1",
        "request_id": request_id,
        "conversation_id": session,
        "tenant_id": tenant,
        "user_id": user,
        "agent_release_id": str(RELEASE),
        "message": "提供一般工作建议",
        "history": [],
        "memory_context": memory_context(tenant, user, "customer-service", session),
    }


def hr_body(tenant, user, run):
    payload = {
        "run_id": run,
        "operation_id": "jd",
        "jd_text": "合成岗位要求",
        "maximum_attempts": 3,
        "memory_context": memory_context(tenant, user, "hr"),
    }
    return {
        "context": {
            "traceId": "business-hr",
            "userId": int(user),
            "sourceModule": "hr",
            "actionType": "draft",
        },
        "skillId": 6106,
        "input": json.dumps(payload),
    }


@pytest.mark.asyncio
async def test_real_business_http_published_assets_repair_and_unknown_no_resend(
    context_mysql, tmp_path
):
    async with running_business_app(context_mysql, tmp_path) as (client, provider):
        expected = {}
        customer_scopes = Counter()
        hr_scopes = Counter()
        for tenant in ("synthetic-t1", "synthetic-t2"):
            headers = {"Authorization": "Bearer " + SECRET, "X-Tenant-ID": tenant}
            for user in ("1", "2"):
                other = "2" if user == "1" else "1"
                for index in (1, 2):
                    session = str(uuid4())
                    body = customer_body(
                        tenant, user, session, f"business-{tenant}-{user}-{index}"
                    )
                    path = f"/v1/customer-service/conversations/{session}/messages"
                    before = len(provider.requests)
                    assert (await client.post(path, json=body)).status_code == 401
                    for field, value in (
                        (
                            "tenant_id",
                            "synthetic-t2" if tenant.endswith("1") else "synthetic-t1",
                        ),
                        ("user_id", other),
                        ("session_id", str(uuid4())),
                    ):
                        forged = deepcopy(body)
                        forged["memory_context"]["scope"][field] = value
                        assert (
                            await client.post(path, headers=headers, json=forged)
                        ).status_code == 403
                    other_agent = deepcopy(body)
                    other_agent["memory_context"]["scope"].update(
                        domain="operations", top_level_agent_id="operations"
                    )
                    assert (
                        await client.post(path, headers=headers, json=other_agent)
                    ).status_code == 403
                    assert len(provider.requests) == before
                    response = await client.post(path, headers=headers, json=body)
                    assert response.status_code == 202, response.status_code
                    run = response.json()["run_id"]
                    events = await client.get(f"/v1/customer-service/runs/{run}/events")
                    assert events.status_code == 200
                    completed = "event: answer.completed" in events.text
                    assert completed, "客服真实Graph未完成；不输出SSE正文"
                    # SSE在此仅等待执行结束，不充当内部读API的用户授权证据。
                    expected[run] = body["memory_context"]["scope"]
                    customer_scopes[(tenant, user)] += 1
                    sent = len(provider.requests)
                    for field, value in (
                        ("user_id", other),
                        ("conversation_id", str(uuid4())),
                    ):
                        changed = deepcopy(body)
                        changed[field] = value
                        scope_key = (
                            "session_id" if field == "conversation_id" else field
                        )
                        changed["memory_context"]["scope"][scope_key] = value
                        changed_path = f"/v1/customer-service/conversations/{changed['conversation_id']}/messages"
                        assert (
                            await client.post(
                                changed_path, headers=headers, json=changed
                            )
                        ).status_code == 409
                    assert len(provider.requests) == sent
        assert len(expected) == 8
        assert set(customer_scopes.values()) == {2} and len(customer_scopes) == 4
        assert provider.calls["customer-service:intent"] == 10
        assert provider.calls["customer-service:answer_general"] == 8
        assert len(provider.requests) == 18

        for tenant in ("synthetic-t1", "synthetic-t2"):
            headers = {"Authorization": "Bearer " + SECRET, "X-Tenant-ID": tenant}
            for user in ("1", "2"):
                other = "2" if user == "1" else "1"
                for index in (1, 2):
                    run = "business-hr-" + uuid4().hex
                    await seed_hr_run(context_mysql, run, tenant)
                    body = hr_body(tenant, user, run)
                    before = len(provider.requests)
                    assert (
                        await client.post("/skill/execute", json=body)
                    ).status_code == 401
                    for field, value in (
                        ("user_id", other),
                        (
                            "tenant_id",
                            "synthetic-t2" if tenant.endswith("1") else "synthetic-t1",
                        ),
                    ):
                        forged = deepcopy(body)
                        payload = json.loads(forged["input"])
                        payload["memory_context"]["scope"][field] = value
                        forged["input"] = json.dumps(payload)
                        assert (
                            await client.post(
                                "/skill/execute", headers=headers, json=forged
                            )
                        ).status_code == 403
                    history = deepcopy(body)
                    payload = json.loads(history["input"])
                    payload["history"] = []
                    history["input"] = json.dumps(payload)
                    assert (
                        await client.post(
                            "/skill/execute", headers=headers, json=history
                        )
                    ).status_code == 422
                    session = deepcopy(body)
                    payload = json.loads(session["input"])
                    payload["memory_context"]["scope"].update(
                        session_kind="CONVERSATION", session_id="forged-history"
                    )
                    session["input"] = json.dumps(payload)
                    assert (
                        await client.post(
                            "/skill/execute", headers=headers, json=session
                        )
                    ).status_code == 403
                    assert len(provider.requests) == before
                    response = await client.post(
                        "/skill/execute", headers=headers, json=body
                    )
                    assert response.status_code == 200, response.status_code
                    result = json.loads(response.json()["content"])["data"]
                    assert result == {"candidates": []}
                    expected[run] = json.loads(body["input"])["memory_context"]["scope"]
                    hr_scopes[(tenant, user)] += 1
                    sent = len(provider.requests)
                    # 已认证第二actor不能借同tenant原run/op读取第一actor缓存结果。
                    replay = hr_body(tenant, other, run)
                    rejected = await client.post(
                        "/skill/execute", headers=headers, json=replay
                    )
                    assert rejected.status_code in {403, 409}, (
                        "HR同run/op跨actor必须拒绝"
                    )
                    changed = deepcopy(body)
                    payload = json.loads(changed["input"])
                    payload["jd_text"] = "不同的合成输入"
                    changed["input"] = json.dumps(payload)
                    rejected = await client.post(
                        "/skill/execute", headers=headers, json=changed
                    )
                    assert rejected.status_code in {409, 422}
                    assert len(provider.requests) == sent
        assert len(expected) == 16
        assert set(hr_scopes.values()) == {2} and len(hr_scopes) == 4
        assert provider.calls["hr:hr.jd.draft"] == 10
        assert len(provider.requests) == 28

        tenant, user = "synthetic-t2", "2"
        headers = {"Authorization": "Bearer " + SECRET, "X-Tenant-ID": tenant}
        unknown_run = "business-unknown-" + uuid4().hex
        await seed_hr_run(context_mysql, unknown_run, tenant)
        provider.unknown = True
        unknown_body = hr_body(tenant, user, unknown_run)
        expected[unknown_run] = json.loads(unknown_body["input"])["memory_context"][
            "scope"
        ]
        first = await client.post("/skill/execute", headers=headers, json=unknown_body)
        assert first.status_code == 422
        before_replay = len(provider.requests)
        repeat = await client.post("/skill/execute", headers=headers, json=unknown_body)
        assert repeat.status_code in {409, 422}
        assert len(provider.requests) == before_replay == 29
        tool_counts = [
            len(dict(request.options.items).get("tools", ()))
            for request in provider.requests
        ]
        assert tool_counts == [0] * 29, "GENERAL_QUERY与HR实际ProviderRequest不含工具"

        async with context_mysql.connect() as connection:
            raw = (
                (
                    await connection.execute(
                        text("SELECT metadata_json FROM agent_context_manifest")
                    )
                )
                .scalars()
                .all()
            )
            stages = (
                await connection.execute(
                    text("SELECT status,current_slot FROM agent_context_stage")
                )
            ).all()
            operations = (
                (
                    await connection.execute(
                        text("SELECT status FROM agent_context_operation")
                    )
                )
                .scalars()
                .all()
            )
            snapshots = (
                (
                    await connection.execute(
                        text(
                            "SELECT referenced_snapshot_json FROM agent_run_prompt_snapshot"
                        )
                    )
                )
                .scalars()
                .all()
            )
            releases = (
                await connection.execute(
                    text("SELECT COUNT(*) FROM agent_release_bundle")
                )
            ).scalar_one()
        assert len(raw) == len(operations) == len(provider.requests) == 29
        assert Counter(operations) == {"UNKNOWN": 1, "SUCCEEDED": 28}
        assert Counter(stages) == {
            ("SUCCEEDED", 3): 2,
            ("SUCCEEDED", 1): 22,
            ("UNKNOWN", 1): 1,
        }
        assert len(snapshots) == 9 and releases == 1
        manifests = [json.loads(row) if isinstance(row, str) else row for row in raw]
        observed = set()
        for manifest in manifests:
            execution = manifest["scope"]["execution_id"]
            scope = manifest["scope"]["conversation"]
            assert scope == expected[execution]
            observed.add(execution)
            assert manifest["measurement"]["total_upper_bound"] > 0
            assert manifest["decision"]["status"] == "ALLOW"
            contains_body = "合成岗位要求" in str(manifest)
            assert not contains_body, "Manifest不得包含正文"
            if scope["domain"] == "hr":
                assert (
                    scope["session_kind"] == "TASK_ONLY" and scope["session_id"] is None
                )
        assert observed == expected.keys()
        assert all("合成岗位要求" not in str(snapshot) for snapshot in snapshots)
