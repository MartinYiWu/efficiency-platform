"""跨语言验收专用本机Agent与合成上游，不读取真实配置或访问外部网络。"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from efficiency_platform_agent.agents.customer_service.graph import CustomerServiceGraph
from efficiency_platform_agent.agents.customer_service.model_gateway import (
    ReleaseStructuredModelGateway,
)
from efficiency_platform_agent.agents.customer_service.release_bundle import (
    ModelPolicy,
    PromptBinding,
)
from efficiency_platform_agent.agents.customer_service.service import (
    CustomerServiceRunService,
)
from efficiency_platform_agent.api.customer_service_routes import (
    build_customer_service_router,
)
from efficiency_platform_agent.api.paid_budget_scope import PaidBudgetScopeMiddleware
from efficiency_platform_agent.core.paid_budget import PaidBudgetPlan, PaidPriceLimit
from efficiency_platform_agent.harness.hr_factory import internal_hr_authorizer
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from efficiency_platform_agent.providers.deepseek_stream import (
    DeepSeekStreamingProvider,
)
from efficiency_platform_agent.providers.paid_http import PaidHttpTransport

RELEASE_ID = UUID("00000000-0000-0000-0000-000000000001")
SCENARIOS = (
    "success",
    "exhaust",
    "retry",
    "cancel",
    "concurrent",
    "tokens",
    "money",
    "unauthorized",
)


def build_fixture(port: int, workdir: Path) -> FastAPI:
    if not 1 <= port <= 65535:
        raise ValueError("invalid loopback port")
    workdir.mkdir(parents=True, exist_ok=True)
    clients: list[httpx.AsyncClient] = []
    services: list[CustomerServiceRunService] = []
    ledgers: dict[str, SqlitePaidBudgetLedger] = {}
    counts = dict.fromkeys(SCENARIOS, 0)
    policy = ModelPolicy(
        policy_key="synthetic",
        semantic_version="1",
        provider="synthetic",
        model_name="synthetic",
        temperature=0,
        top_p=1,
        max_input_tokens=200000,
        max_output_tokens=512,
        connect_timeout_ms=1000,
        read_timeout_ms=15000,
        max_retries=0,
        checksum="a" * 64,
    )
    bindings = tuple(
        PromptBinding(
            stage_key=stage,
            ordinal=1,
            prompt_key=stage,
            prompt_version="1",
            checksum="a" * 64,
            messages=(
                {
                    "ordinal": 1,
                    "role": "SYSTEM",
                    "message_key": stage,
                    "content_template": "synthetic-stage:" + stage,
                    "content_format": "TEXT",
                    "trusted_instruction": True,
                    "checksum": "a" * 64,
                    "variables": (),
                },
                {
                    "ordinal": 2,
                    "role": "USER",
                    "message_key": stage + "_input",
                    "content_template": "{{input_json}}",
                    "content_format": "JSON",
                    "trusted_instruction": False,
                    "checksum": "a" * 64,
                    "variables": (),
                },
            ),
        )
        for stage in ("intent", "answer_general")
    )
    release = SimpleNamespace(
        contract_version="customer-service-release/1",
        model_policy=policy,
        large_context_model_policy=None,
        rag_policy=SimpleNamespace(rewrite_query_limit=1),
        prompt_bindings=bindings,
    )

    class Releases:
        async def get(self, release_id):
            return release if release_id == RELEASE_ID else None

    class NoRetrieval:
        async def search(self, **kwargs):
            raise AssertionError("synthetic GENERAL path cannot use real knowledge")

    @asynccontextmanager
    async def lifespan(app):
        yield
        for service in services:
            for run in service._runs.values():
                if run.task and not run.task.done():
                    run.task.cancel()
        await asyncio.gather(
            *(
                run.task
                for service in services
                for run in service._runs.values()
                if run.task
            ),
            return_exceptions=True,
        )
        for client in clients:
            await client.aclose()

    app = FastAPI(lifespan=lifespan)

    @app.get("/health/ready")
    async def ready():
        return {"status": "ok", "kind": "loopback-test-fixture"}

    @app.post("/test-upstream/{scenario}/chat/completions")
    async def upstream(scenario: str, request: Request):
        if scenario not in SCENARIOS:
            raise ValueError("unknown scenario")
        counts[scenario] += 1
        payload = await request.json()
        if scenario == "retry" and counts[scenario] == 1:
            return StreamingResponse(iter(()), status_code=429)
        intent = any(
            "synthetic-stage:intent" in message.get("content", "")
            for message in payload["messages"]
        )
        if scenario == "cancel" and not intent:
            await asyncio.sleep(10)
        content = (
            {
                "intent_type": "GENERAL_QUERY",
                "requires_company_knowledge": False,
                "requires_general_advice": True,
                "normalized_question": "synthetic question",
                "retrieval_queries": [],
            }
            if intent
            else {
                "contract_version": "customer-service-answer/1",
                "answer_mode": "GENERAL_ADVICE",
                "knowledge_gap": None,
                "company_sections": [],
                "general_advice": {
                    "title": "通用建议，非公司制度",
                    "paragraphs": ["本机合成回答，用于成本保护验收。"],
                },
                "clarification_question": None,
                "insufficiency_reason": None,
            }
        )
        event = {
            "choices": [
                {
                    "delta": {"content": json.dumps(content, ensure_ascii=False)},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "completion_tokens_details": {"reasoning_tokens": 0},
            },
        }

        async def stream():
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/test/observations/{scenario}")
    async def observations(scenario: str):
        return {
            "scenario": scenario,
            "upstream_requests": counts[scenario],
            "snapshot": ledgers[scenario].snapshot(),
            "details": ledgers[scenario].details(),
        }

    for scenario in SCENARIOS:
        ledger = SqlitePaidBudgetLedger(workdir / (scenario + ".sqlite3"))
        if scenario != "unauthorized":
            ledger.authorize(
                PaidBudgetPlan(
                    scenario,
                    3 if scenario == "concurrent" else 30,
                    10 if scenario == "money" else 10000,
                    int(time.time() * 1000) + 120000,
                    1 if scenario == "exhaust" else 10,
                    10000,
                    30000,
                    3,
                    3,
                    2000000,
                    10000,
                    10000,
                    2000000,
                    512 if scenario == "tokens" else 10000,
                    10000,
                ),
                (
                    PaidPriceLimit(
                        "deepseek",
                        "synthetic",
                        200000,
                        512,
                        10,
                        "synthetic localhost test only",
                        "synthetic-v1",
                        200000,
                        1,
                        0,
                        1,
                    ),
                ),
            )
        ledgers[scenario] = ledger
        endpoint = f"http://127.0.0.1:{port}/test-upstream/{scenario}/chat/completions"
        client = httpx.AsyncClient(
            transport=PaidHttpTransport(
                ledger,
                httpx.AsyncHTTPTransport(retries=0),
                "deepseek",
                allowed_url=endpoint,
            ),
            trust_env=False,
        )
        clients.append(client)
        provider = DeepSeekStreamingProvider(
            client,
            "synthetic",
            api_key="synthetic-not-a-secret",
            base_url=f"http://127.0.0.1:{port}/test-upstream/{scenario}",
            timeout_ms=15000,
            max_retries=1,
        )
        service = CustomerServiceRunService(
            CustomerServiceGraph(NoRetrieval()),
            Releases(),
            lambda bundle, selected=provider: ReleaseStructuredModelGateway(
                selected, bundle
            ),
        )
        services.append(service)
        child = FastAPI()
        child.add_middleware(PaidBudgetScopeMiddleware)
        child.include_router(
            build_customer_service_router(
                service,
                internal_hr_authorizer("paid-chain-synthetic-internal-secret-000"),
            )
        )
        app.mount("/" + scenario, child)
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    args = parser.parse_args()
    uvicorn.run(
        build_fixture(args.port, args.workdir),
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
    )
