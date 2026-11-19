"""一个实际CSR知识路径：受控改写→真member元数据投影→充分性→知识回答；无DB/付费。"""

import json
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest

from efficiency_platform_agent.agents.customer_service.memory_lineage import (
    validate_evidence,
)
from efficiency_platform_agent.agents.customer_service.model_gateway import (
    ReleaseStructuredModelGateway,
    _freeze,
    _stage_thinking_option,
)
from efficiency_platform_agent.agents.customer_service.release_bundle import (
    PromptBinding,
)
from efficiency_platform_agent.agents.customer_service.retrieval import (
    CustomerServiceRetrieval,
)
from efficiency_platform_agent.agents.customer_service.state import (
    CustomerServiceAnswer,
    QueryRewrite,
    SufficiencyDecision,
)
from efficiency_platform_agent.agents.customer_service.vector_repository import (
    DocumentChunkRepository,
)
from efficiency_platform_agent.core.context_ports import ContextMetadata
from efficiency_platform_agent.core.memory import SourceDependency
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.core.run_context_binding import bind_run_context
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)
from tests.unit.agents.customer_service.test_evidence_pack import (
    bundle as prompt_bundle,
)
from tests.unit.context.test_memory_agent_policy_matrix import setup


@pytest.mark.asyncio
async def test_csr_knowledge_actual_document_closure_and_source_rejection():
    _, _, _, current, history, provider, binding, manifests, model = setup(
        "customer-service"
    )
    context = binding.memory_context
    assert context is not None
    kb, release, document, version, chunk = (uuid4() for _ in range(5))
    file_sha = "a" * 64
    key = [str(kb), str(release), str(document), str(version), file_sha]
    doc = SourceDependency(
        "KNOWLEDGE_DOCUMENT",
        "document-source",
        sha256(json.dumps(key, separators=(",", ":")).encode()).hexdigest(),
        0,
        1,
        0,
    )
    unused = SourceDependency(
        "KNOWLEDGE_DOCUMENT", "unused-document", "b" * 64, 0, 1, 0
    )
    directory = {
        "schema_version": "knowledge-context/1",
        "tenant_id": "tenant",
        "user_id": "user",
        "documents": [
            {
                "knowledge_base_id": str(kb),
                "index_release_id": str(release),
                "document_id": str(document),
                "document_version_id": str(version),
                "file_sha256": file_sha,
                "source": {
                    "source_type": doc.source_type,
                    "source_id": doc.source_id,
                    "source_version": doc.source_version,
                    "grant_epoch": 0,
                    "source_epoch": 1,
                    "deletion_epoch": 0,
                },
            }
        ],
    }
    stages = {
        "rewrite": QueryRewrite,
        "sufficiency": SufficiencyDecision,
        "answer_company": CustomerServiceAnswer,
    }
    packet = replace(
        context.packet,
        safety_dependencies=(*context.packet.safety_dependencies, doc, unused),
    )
    context = replace(
        context,
        packet=packet,
        policy=replace(
            context.policy,
            source_types=context.policy.source_types | {"KNOWLEDGE_DOCUMENT"},
        ),
        execution_grants=tuple(
            replace(context.execution_grants[0], node_id="customer-service:" + stage)
            for stage in stages
        ),
        packet_digest=memory_packet_digest(packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(packet),
        knowledge_context_json=json.dumps(directory),
    )
    binding = replace(binding, memory_context=context)
    provider.dispatch.authority.memory_execution_store.record = replace(
        provider.dispatch.authority.memory_execution_store.record, context=context
    )
    bundle = prompt_bundle(limit=40000)
    bundle.contract_version = "customer-service-release/1"
    bundle.knowledge_bindings = (
        SimpleNamespace(knowledge_base_id=kb, index_release_id=release),
    )
    bundle.rag_policy = SimpleNamespace(
        rewrite_query_limit=1,
        vector_top_k=2,
        fts_top_k=2,
        fusion_top_k=2,
        rerank_top_k=1,
        context_token_limit=4000,
    )
    bundle.prompt_bindings += tuple(
        PromptBinding(
            stage_key=stage,
            ordinal=1,
            prompt_key=stage,
            prompt_version="1",
            checksum="a" * 64,
            messages=bundle.prompt_bindings[4].messages,
        )
        for stage in ("rewrite",)
    )
    original_meta = next(iter(provider.dispatch.authority._published.values()))[0]
    capacity = replace(original_meta.capacity, context_window_tokens=64000)
    limits = replace(
        original_meta.limits, context_window_tokens=64000, node_input_limit=63900
    )
    for stage, output in stages.items():
        options = JsonObject(
            (
                ("logical_model", "main"),
                ("temperature", 0.0),
                ("top_p", 1.0),
                ("max_tokens", 100),
                ("response_format", JsonObject((("type", "json_object"),))),
                ("json_schema", _freeze(output.model_json_schema())),
            )
            + _stage_thinking_option(stage)
        )
        node = "customer-service:" + stage
        provider.dispatch.authority._published[("fake", "fake", node)] = (
            ContextMetadata(
                node,
                "window/1",
                "prompt/1",
                "tool/1",
                "schema/1",
                0,
                capacity,
                limits,
                options,
            ),
        )
        provider.dispatch.authority._execution_agents[node] = (
            "customer-service",
            "assistant_response",
        )
    text = "当前正式制度明确允许合成步骤。"
    evidence = DocumentChunkRepository._evidence(
        (
            (
                str(chunk),
                str(kb),
                str(document),
                str(version),
                str(release),
                "合成制度",
                1,
                None,
                None,
                text,
                sha256(text.encode()).hexdigest(),
                None,
                None,
                None,
                0.9,
                file_sha,
            ),
        )
    )[0]

    class Repository:
        async def vector_search(self, **kwargs):
            return (evidence,)

        async def fts_search(self, **kwargs):
            return ()

    class Embedding:
        async def embed(self, texts):
            return ((0.0,) * 1024,)

    class Reranker:
        async def rerank(self, query, documents, *, top_n):
            return ((0, 0.9),)

    replies = [
        {"queries": ["制度步骤"]},
        {
            "sufficient": True,
            "supported_claims": [],
            "unsupported_claims": [],
            "conflicts": [],
            "recommended_mode": "COMPANY_KNOWLEDGE",
        },
        {
            "contract_version": "customer-service-answer/1",
            "answer_mode": "COMPANY_KNOWLEDGE",
            "company_sections": [
                {
                    "title": "制度",
                    "paragraphs": [
                        {
                            "text": "按正式制度执行。",
                            "supporting_chunk_ids": [str(chunk)],
                        }
                    ],
                }
            ],
        },
    ]

    async def complete(request):
        model.requests.append(request)
        return ProviderResult(
            "provider-result/1",
            ProviderMessage("assistant", json.dumps(replies.pop(0))),
            ProviderUsage(1, 1, 0, 0, 0),
        )

    model.complete = complete
    gateway = ReleaseStructuredModelGateway(provider, bundle)
    with bind_run_context(binding):
        trace = await CustomerServiceRetrieval(
            Repository(), Embedding(), Reranker()
        ).search(tenant_id="tenant", question="目标", gateway=gateway, bundle=bundle)
        await gateway.complete(
            "sufficiency",
            {
                "question": "目标",
                "evidence": [
                    item.model_dump(mode="json") for item in trace.reranked_evidence
                ],
            },
            SufficiencyDecision,
        )
        await gateway.complete(
            "answer_company",
            {
                "question": "目标",
                "evidence": [
                    item.model_dump(mode="json") for item in trace.reranked_evidence
                ],
            },
            CustomerServiceAnswer,
        )
        before = len(model.requests)
        for changed in (
            evidence.model_copy(update={"document_sha256": "f" * 64}),
            evidence.model_copy(update={"document_version_id": uuid4()}),
        ):
            with pytest.raises(ValueError, match="EVIDENCE_MISMATCH"):
                validate_evidence((changed,))
        assert len(model.requests) == before
    assert len(model.requests) == 3
    assert set(manifests.manifests[0].safety_dependencies) == {current, history}
    assert set(manifests.manifests[-1].safety_dependencies) == {current, history, doc}
    assert unused not in manifests.manifests[-1].safety_dependencies
