from __future__ import annotations

import asyncio
from uuid import UUID

import httpx
from fastapi import FastAPI

from efficiency_platform_agent.agents.customer_service.graph import GraphResult
from efficiency_platform_agent.agents.customer_service.renderer import render_answer
from efficiency_platform_agent.agents.customer_service.service import (
    CustomerServiceRunService,
)
from efficiency_platform_agent.agents.customer_service.state import (
    AnswerMode,
    CustomerServiceAnswer,
    GeneralAdvice,
)
from efficiency_platform_agent.api.customer_service_routes import (
    build_customer_service_router,
)

RELEASE_ID = UUID("80000000-0000-0000-0000-000000000001")
CONVERSATION_ID = UUID("80000000-0000-0000-0000-000000000002")


class Releases:
    async def get(self, release_id):
        return object() if release_id == RELEASE_ID else None

    async def get_active(self):
        return RELEASE_ID, object()


class Graph:
    async def run(self, request, bundle, gateway):
        await asyncio.sleep(0)
        answer = CustomerServiceAnswer(
            contract_version="customer-service-answer/1",
            answer_mode=AnswerMode.GENERAL_ADVICE,
            general_advice=GeneralAdvice(paragraphs=("可以先列出问题清单。",)),
        )
        return GraphResult(rendered=render_answer(answer, ()), stage_summaries=(("intent", "已识别 GENERAL_QUERY"),))


def app() -> FastAPI:
    value = FastAPI()
    service = CustomerServiceRunService(Graph(), Releases(), lambda _: object())  # type: ignore[arg-type]
    value.include_router(build_customer_service_router(service))
    return value


async def test_submit_and_sse_events_are_ordered_and_resumable() -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app()), base_url="http://test") as client:
        response = await client.post(
            f"/v1/customer-service/conversations/{CONVERSATION_ID}/messages",
            json={
                "contract_version": "customer-service-run/1",
                "request_id": "req-1",
                "conversation_id": str(CONVERSATION_ID),
                "tenant_id": "tenant-1",
                "user_id": "user-1",
                "agent_release_id": str(RELEASE_ID),
                "message": "怎么梳理问题？",
                "history": [],
            },
        )
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        stream = await client.get(f"/v1/customer-service/runs/{run_id}/events")
        assert stream.status_code == 200
        assert stream.text.index("event: answer.delta") < stream.text.index("event: answer.completed")
        resumed = await client.get(f"/v1/customer-service/runs/{run_id}/events", headers={"Last-Event-ID": "2"})
        assert "id: 1\n" not in resumed.text
        assert "id: 2\n" not in resumed.text


async def test_unknown_fields_are_rejected() -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app()), base_url="http://test") as client:
        response = await client.post(
            f"/v1/customer-service/conversations/{CONVERSATION_ID}/messages",
            json={
                "contract_version": "customer-service-run/1",
                "request_id": "req-2",
                "conversation_id": str(CONVERSATION_ID),
                "tenant_id": "tenant-1",
                "user_id": "user-1",
                "agent_release_id": str(RELEASE_ID),
                "message": "问题",
                "history": [],
                "unexpected": True,
            },
        )
        assert response.status_code == 422
