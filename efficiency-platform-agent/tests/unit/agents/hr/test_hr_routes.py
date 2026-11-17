import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from efficiency_platform_agent.api.hr_skill_routes import build_hr_skill_router


@pytest.mark.asyncio
async def test_unconfigured_hr_route_fails_closed():
    app = FastAPI()
    app.include_router(build_hr_skill_router(None, None))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        result = await client.post(
            "/skill/execute",
            json={
                "context": {
                    "traceId": "t",
                    "userId": 1,
                    "sourceModule": "aihub",
                    "actionType": "hr",
                },
                "skillId": 6106,
                "input": "{}",
            },
        )
    assert result.status_code == 503


@pytest.mark.asyncio
async def test_authorized_extract_endpoint_and_tenant_mismatch():
    import base64
    import hashlib
    import json

    from efficiency_platform_agent.agents.hr.service import HrSkillService
    from efficiency_platform_agent.api.hr_skill_routes import HrSkillEndpoint
    from efficiency_platform_agent.core.execution_control import RunControl

    class Controls:
        def __init__(self):
            self.control = RunControl()

        async def get(self, tenant, run, maximum_attempts=3):
            assert tenant == "tenant-a"
            return self.control

        async def cancel(self, tenant, run):
            self.control.stop()

    async def authorize(request):
        if request.headers.get("Authorization") != "Bearer internal-test":
            raise PermissionError()
        return "tenant-a"

    app = FastAPI()
    app.include_router(
        build_hr_skill_router(
            HrSkillEndpoint(HrSkillService(None, None), Controls()), authorize
        )
    )
    content = "姓名：张三\nPython".encode()
    body = {
        "context": {
            "traceId": "t",
            "userId": 1,
            "sourceModule": "aihub",
            "actionType": "hr",
        },
        "skillId": 6101,
        "input": json.dumps(
            {
                "run_id": "r",
                "operation_id": "o",
                "extraction": {
                    "filename": "r.txt",
                    "content_base64": base64.b64encode(content).decode(),
                    "sha256": hashlib.sha256(content).hexdigest(),
                },
            }
        ),
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post("/skill/execute", json=body)).status_code == 401
        assert (
            await client.post(
                "/skill/execute",
                json=body,
                headers={
                    "Authorization": "Bearer internal-test",
                    "X-Tenant-ID": "other",
                },
            )
        ).status_code == 403
        result = await client.post(
            "/skill/execute",
            json=body,
            headers={
                "Authorization": "Bearer internal-test",
                "X-Tenant-ID": "tenant-a",
            },
        )
    assert result.status_code == 200
    data = json.loads(result.json()["content"])["data"]
    assert data["identity"]["name"]["value"] == "张三"
    assert "张三" not in str(data["cleaned_blocks"])


@pytest.mark.asyncio
async def test_cancel_existing_skill_endpoint_requires_auth_and_never_creates_run():
    import json

    from efficiency_platform_agent.agents.hr.service import HrSkillService
    from efficiency_platform_agent.api.hr_skill_routes import HrSkillEndpoint

    class Controls:
        def __init__(self):
            self.cancelled = []
            self.get_calls = 0

        async def get(self, tenant, run, maximum_attempts=3):
            self.get_calls += 1
            raise AssertionError("取消不得调用get创建run")

        async def cancel(self, tenant, run):
            self.cancelled.append((tenant, run))

    controls = Controls()

    async def authorize(request):
        if request.headers.get("Authorization") != "Bearer service":
            raise PermissionError()
        return "tenant-a"

    app = FastAPI()
    app.include_router(
        build_hr_skill_router(
            HrSkillEndpoint(HrSkillService(None, None), controls), authorize
        )
    )
    body = {
        "context": {
            "traceId": "t",
            "userId": 1,
            "sourceModule": "aihub",
            "actionType": "hr",
        },
        "skillId": 6107,
        "input": json.dumps({"run_id": "existing", "operation_id": "cancel"}),
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post("/skill/execute", json=body)).status_code == 401
        assert controls.cancelled == []
        assert (
            await client.post(
                "/skill/execute",
                json=body,
                headers={"Authorization": "Bearer service", "X-Tenant-ID": "tenant-b"},
            )
        ).status_code == 403
        result = await client.post(
            "/skill/execute",
            json=body,
            headers={"Authorization": "Bearer service", "X-Tenant-ID": "tenant-a"},
        )
    assert result.status_code == 200
    assert json.loads(result.json()["content"])["data"]["cancelled"] is True
    assert controls.cancelled == [("tenant-a", "existing")]
    assert controls.get_calls == 0


@pytest.mark.asyncio
async def test_cancel_persists_across_control_store_reopen_and_tenant_scope(tmp_path):
    from efficiency_platform_agent.core.paid_budget import PaidBudgetError
    from efficiency_platform_agent.harness.hr_factory import PersistentHrRunControlStore
    from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger

    ledger = SqlitePaidBudgetLedger(tmp_path / "fake-only.sqlite3")
    first = PersistentHrRunControlStore(ledger)
    await first.get("tenant-a", "same-run")
    await first.get("tenant-b", "same-run")
    await first.cancel("tenant-a", "same-run")
    reopened = PersistentHrRunControlStore(
        SqlitePaidBudgetLedger(tmp_path / "fake-only.sqlite3")
    )
    with pytest.raises(PaidBudgetError, match="execution already stopped|任务|stopped"):
        await reopened.get("tenant-a", "same-run")
    assert (await reopened.get("tenant-b", "same-run")).stopped is None


@pytest.mark.asyncio
async def test_endpoint_deadline_interrupts_provider_and_stops_further_stages(monkeypatch):
    import asyncio

    from efficiency_platform_agent.agents.hr.service import HrSkillService
    from efficiency_platform_agent.api.hr_skill_routes import HrSkillEndpoint
    from efficiency_platform_agent.contracts.hr import FactOutput, HrSkillRequest
    from efficiency_platform_agent.core.execution_control import (
        RunControl,
        consume_http_attempt,
    )
    from efficiency_platform_agent.core.paid_budget import PaidBudgetError
    from tests.unit.agents.hr.test_hr_service import FakeAssembler

    entered = asyncio.Event()
    timeouts = []
    original_timeout_at = asyncio.timeout_at

    def controlled_timeout_at(deadline):
        # 仅推迟测试的计时起点，进入Provider后仍由真实asyncio超时取消。
        timeout = original_timeout_at(None)
        timeouts.append(timeout)
        return timeout

    monkeypatch.setattr(asyncio, "timeout_at", controlled_timeout_at)

    class Provider:
        calls = 0
        closed = False

        async def complete(self, request):
            consume_http_attempt()
            self.calls += 1
            try:
                entered.set()
                await asyncio.Event().wait()
            finally:
                self.closed = True

    class Controls:
        def __init__(self):
            self.control = RunControl()

        async def get(self, tenant, run, maximum_attempts=3):
            return self.control

        async def cancel(self, tenant, run):
            await self.control.close()

    controls = Controls()
    provider = Provider()
    endpoint = HrSkillEndpoint(
        HrSkillService(FakeAssembler(FactOutput), provider), controls
    )
    request = HrSkillRequest(run_id="deadline-run", operation_id="operation")

    async def expire_after_provider_enters():
        await entered.wait()
        deadline = asyncio.get_running_loop().time()
        controls.control.deadline = deadline
        timeouts[0].reschedule(deadline)

    expiry = asyncio.create_task(expire_after_provider_enters())
    with pytest.raises(PaidBudgetError):
        await endpoint.execute("tenant", 6102, request)
    await expiry
    assert controls.control.stopped == "AGENT_TASK_DEADLINE"
    assert provider.closed and provider.calls == 1, (
        f"calls={provider.calls}, closed={provider.closed}, "
        f"stopped={controls.control.stopped}"
    )
    with pytest.raises(PaidBudgetError):
        await endpoint.execute("tenant", 6102, request)
    assert provider.calls == 1
