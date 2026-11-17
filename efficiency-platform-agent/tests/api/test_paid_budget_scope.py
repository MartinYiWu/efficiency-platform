"""HTTP范围由服务端产生，后台任务继承且不接受客户端预算标识。"""

import asyncio

import httpx
from fastapi import FastAPI

from efficiency_platform_agent.api.paid_budget_scope import PaidBudgetScopeMiddleware
from efficiency_platform_agent.core.paid_budget import current_paid_scope


async def test_scope_ignores_user_headers_and_is_inherited_by_child_task():
    app = FastAPI()
    app.add_middleware(PaidBudgetScopeMiddleware)

    @app.post("/call")
    async def call():
        async def child():
            return current_paid_scope()

        return {
            "parent": current_paid_scope(),
            "child": await asyncio.create_task(child()),
        }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local"
    ) as client:
        first = (
            await client.post(
                "/call", headers={"X-Budget-ID": "free", "X-Run-ID": "fresh"}
            )
        ).json()
        second = (await client.post("/call")).json()
    assert first["parent"] == first["child"]
    assert first["parent"].startswith("http-")
    assert first["parent"] != second["parent"]
    assert current_paid_scope() == "unscoped"
