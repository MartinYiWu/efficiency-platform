from __future__ import annotations

import asyncio
import logging
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID

import httpx
from fastapi import FastAPI

from efficiency_platform_agent.agents.customer_service.evidence_assembly import (
    EvidenceAssembly,
)
from efficiency_platform_agent.agents.customer_service.graph import GraphResult
from efficiency_platform_agent.agents.customer_service.renderer import render_answer
from efficiency_platform_agent.agents.customer_service.retrieval import RetrievalTrace
from efficiency_platform_agent.agents.customer_service.service import (
    CustomerServiceRunService,
)
from efficiency_platform_agent.agents.customer_service.state import (
    AnswerMode,
    CustomerServiceAnswer,
    CustomerServiceRunRequest,
    DebugKnowledgeBinding,
    DebugRequest,
    Evidence,
    GeneralAdvice,
    ParentEvidence,
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
        return GraphResult(
            rendered=render_answer(answer, ()),
            stage_summaries=(("intent", "已识别 GENERAL_QUERY"),),
        )


def app() -> FastAPI:
    value = FastAPI()
    service = CustomerServiceRunService(Graph(), Releases(), lambda _: object())  # type: ignore[arg-type]
    value.include_router(build_customer_service_router(service))
    return value


async def test_submit_and_sse_events_are_ordered_and_resumable() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://test"
    ) as client:
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
        assert stream.text.index("event: answer.delta") < stream.text.index(
            "event: answer.completed"
        )
        resumed = await client.get(
            f"/v1/customer-service/runs/{run_id}/events", headers={"Last-Event-ID": "2"}
        )
        assert "id: 1\n" not in resumed.text
        assert "id: 2\n" not in resumed.text


async def test_unknown_fields_are_rejected() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://test"
    ) as client:
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


async def test_background_failure_writes_safe_diagnostic_log(caplog) -> None:
    class FailingGraph:
        async def run(self, request, bundle, gateway):
            raise RuntimeError("provider-secret-must-not-be-logged")

    service = CustomerServiceRunService(
        FailingGraph(),
        Releases(),
        lambda _: object(),  # type: ignore[arg-type]
    )
    request = {
        "contract_version": "customer-service-run/1",
        "request_id": "req-failure-log",
        "conversation_id": str(CONVERSATION_ID),
        "tenant_id": "tenant-1",
        "user_id": "user-1",
        "agent_release_id": str(RELEASE_ID),
        "message": "问题",
        "history": [],
    }
    failure_app = FastAPI()
    failure_app.include_router(build_customer_service_router(service))
    with caplog.at_level(logging.ERROR, logger="CustomerServiceRun"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=failure_app), base_url="http://test"
        ) as client:
            response = await client.post(
                f"/v1/customer-service/conversations/{CONVERSATION_ID}/messages",
                json=request,
            )
            run_id = response.json()["run_id"]
            await client.get(f"/v1/customer-service/runs/{run_id}/events")

    log = caplog.text
    assert "event=customer_service_run_failed" in log
    assert "error_type=RuntimeError" in log
    assert "provider-secret-must-not-be-logged" not in log


async def test_rag_debug_uses_requested_tenant_for_retrieval() -> None:
    knowledge_base_id = UUID("80000000-0000-0000-0000-000000000003")
    index_release_id = UUID("80000000-0000-0000-0000-000000000004")
    requested_knowledge_base_id = UUID("80000000-0000-0000-0000-000000000013")
    requested_index_release_id = UUID("80000000-0000-0000-0000-000000000014")

    class DebugGraph(Graph):
        request = None
        bundle = None

        async def run(self, request, bundle, gateway):
            self.request = request
            self.bundle = bundle
            return await super().run(request, bundle, gateway)

    class DebugBundle(SimpleNamespace):
        def model_copy(self, *, update):
            return DebugBundle(**(vars(self) | update))

    class DebugReleases:
        async def get(self, release_id):
            return DebugBundle(
                knowledge_bindings=(
                    SimpleNamespace(
                        knowledge_base_id=knowledge_base_id,
                        index_release_id=index_release_id,
                    ),
                )
            )

    graph = DebugGraph()
    service = CustomerServiceRunService(  # type: ignore[arg-type]
        graph, DebugReleases(), lambda _: object()
    )
    await service.debug(
        DebugRequest(
            contract_version="customer-service-rag-debug/1",
            agent_key="customer-service",
            tenant_id="dev",
            question="发布流程是什么？",
            agent_release_id=RELEASE_ID,
            agent_version_id=RELEASE_ID,
            rag_policy_version_id=RELEASE_ID,
            knowledge_bindings=(
                DebugKnowledgeBinding(
                    knowledge_base_id=requested_knowledge_base_id,
                    index_release_id=requested_index_release_id,
                ),
            ),
        )
    )

    assert graph.request is not None
    assert graph.request.tenant_id == "dev"
    assert graph.bundle.knowledge_bindings[0].knowledge_base_id == requested_knowledge_base_id
    assert graph.bundle.knowledge_bindings[0].index_release_id == requested_index_release_id


async def test_rag_debug_exposes_child_parent_mapping_and_budget() -> None:
    parent_id = UUID("80000000-0000-0000-0000-000000000099")
    child_id = UUID("80000000-0000-0000-0000-000000000098")
    content = "员工应提前申请，紧急情况可事后补交证明。"
    child_content = "事后补交证明"
    child = Evidence(
        chunk_id=child_id,
        parent_id=parent_id,
        knowledge_base_id=UUID("80000000-0000-0000-0000-000000000003"),
        document_id=UUID("80000000-0000-0000-0000-000000000097"),
        document_version_id=UUID("80000000-0000-0000-0000-000000000096"),
        index_release_id=UUID("80000000-0000-0000-0000-000000000004"),
        document_title="请假制度",
        version_no=2,
        content=child_content,
        content_hash=sha256(child_content.encode()).hexdigest(),
        score=0.91,
    )
    selected = child.model_copy(
        update={
            "content": content,
            "content_hash": sha256(content.encode()).hexdigest(),
            "hit_content": child_content,
            "hit_content_hash": child.content_hash,
            "hit_start_offset": content.index(child_content),
            "hit_end_offset": content.index(child_content) + len(child_content),
        }
    )
    assembly = EvidenceAssembly(
        selected=(selected,),
        selected_parents=(
            ParentEvidence(
                parent_id=parent_id,
                knowledge_base_id=child.knowledge_base_id,
                document_id=child.document_id,
                document_version_id=child.document_version_id,
                index_release_id=child.index_release_id,
                document_title=child.document_title,
                version_no=child.version_no,
                page_no=1,
                page_end=2,
                content=content,
                content_hash=sha256(content.encode()).hexdigest(),
                token_count=30,
            ),
        ),
        hit_chunk_ids={parent_id: (child_id,)},
        excluded_parent_ids=(),
        duplicate_parent_ids=(),
        context_token_limit=8000,
        used_tokens=4500,
    )

    class DebugGraph(Graph):
        async def run(self, request, bundle, gateway):
            baseline = await super().run(request, bundle, gateway)
            trace = RetrievalTrace(
                "事后补交？",
                ("事后补交",),
                (child.index_release_id,),
                (child,),
                (),
                (child,),
                (child,),
                assembly,
            )
            return GraphResult(
                baseline.rendered, (("retrieval", "证据已组装"),), (selected,), trace
            )

    class DebugBundle(SimpleNamespace):
        def model_copy(self, *, update):
            return DebugBundle(**(vars(self) | update))

    class DebugReleases:
        async def get(self, release_id):
            return DebugBundle(
                knowledge_bindings=(
                    SimpleNamespace(
                        knowledge_base_id=child.knowledge_base_id,
                        index_release_id=child.index_release_id,
                    ),
                )
            )

    service = CustomerServiceRunService(
        DebugGraph(),
        DebugReleases(),
        lambda _: object(),  # type: ignore[arg-type]
    )
    response = await service.debug(
        DebugRequest(
            contract_version="customer-service-rag-debug/1",
            agent_key="customer-service",
            tenant_id="dev",
            question="事后补交？",
            agent_release_id=RELEASE_ID,
            agent_version_id=RELEASE_ID,
            rag_policy_version_id=RELEASE_ID,
            knowledge_bindings=(
                DebugKnowledgeBinding(
                    knowledge_base_id=child.knowledge_base_id,
                    index_release_id=child.index_release_id,
                ),
            ),
        )
    )
    assert response["child_hits"][0]["parent_id"] == str(parent_id)
    assert response["vector_candidates"][0]["chunk_id"] == str(child_id)
    assert response["fused_candidates"][0]["chunk_id"] == str(child_id)
    assert response["parent_evidence"][0]["content"] == content
    assert response["parent_evidence"][0]["page_start"] == 1
    assert response["parent_evidence"][0]["page_end"] == 2
    assert response["budget_usage"]["used_tokens"] == 4500
    assert "citations" in response
    assert response["citations"] == []
    run = await service.submit(
        CustomerServiceRunRequest(
            contract_version="customer-service-run/1",
            request_id="parent-replay",
            conversation_id=CONVERSATION_ID,
            tenant_id="dev",
            user_id="user-1",
            agent_release_id=RELEASE_ID,
            message="事后补交？",
            history=(),
        )
    )
    events = [event async for event in service.events(run.run_id)]
    retrieval_event = next(
        event for event in events if event.payload.stage == "retrieval"
    )
    assert (
        retrieval_event.payload.retrieval_facts["parent_evidence"][0]["content"]
        == content
    )
