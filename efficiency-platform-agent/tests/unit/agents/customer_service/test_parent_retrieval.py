"""子片段重排后展开完整父证据。"""

from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest

from efficiency_platform_agent.agents.customer_service.retrieval import (
    CustomerServiceRetrieval,
)
from efficiency_platform_agent.agents.customer_service.state import (
    Evidence,
    ParentEvidence,
    QueryRewrite,
)


@pytest.mark.asyncio
async def test_retrieval_expands_reranked_child_to_complete_parent() -> None:
    parent_id = uuid4()
    release_id = uuid4()
    content = "员工应提前申请，紧急情况允许事后补交证明。"
    child = Evidence(
        chunk_id=uuid4(),
        parent_id=parent_id,
        knowledge_base_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        index_release_id=release_id,
        document_title="请假制度",
        version_no=1,
        content="事后补交证明",
        content_hash=sha256("事后补交证明".encode()).hexdigest(),
        score=0.8,
    )
    parent = ParentEvidence(
        parent_id=parent_id,
        knowledge_base_id=child.knowledge_base_id,
        document_id=child.document_id,
        document_version_id=child.document_version_id,
        index_release_id=release_id,
        document_title="请假制度",
        version_no=1,
        content=content,
        content_hash=sha256(content.encode()).hexdigest(),
        token_count=25,
    )

    class Repository:
        async def vector_search(self, **_kwargs):
            return (child,)

        async def fts_search(self, **_kwargs):
            return ()

        async def get_parents(self, **_kwargs):
            return (parent,)

    class Gateway:
        async def complete(self, *_args):
            return QueryRewrite(queries=("事后补交证明",))

    class Embedding:
        async def embed(self, _queries):
            return ((0.0,) * 1024,)

    class Reranker:
        async def rerank(self, _query, _documents, *, top_n):
            assert top_n == 1
            return ((0, 0.9),)

    policy = SimpleNamespace(
        rewrite_query_limit=1,
        vector_top_k=5,
        fts_top_k=5,
        fusion_top_k=5,
        rerank_top_k=5,
        context_token_limit=600,
    )
    bundle = SimpleNamespace(
        rag_policy=policy,
        model_policy=SimpleNamespace(max_input_tokens=32000, max_output_tokens=100),
        prompt_bindings=tuple(
            SimpleNamespace(
                stage_key=stage,
                messages=(SimpleNamespace(content_template="规则" * 60),),
            )
            for stage in ("answer_company", "answer_mixed")
        ),
        knowledge_bindings=(SimpleNamespace(index_release_id=release_id),),
    )

    trace = await CustomerServiceRetrieval(
        Repository(), Embedding(), Reranker()
    ).search(
        tenant_id="dev", question="能事后补证明吗？", gateway=Gateway(), bundle=bundle
    )

    assert trace.reranked_evidence[0].content == "事后补交证明"
    assert trace.assembly.selected[0].content == content

    bundle.prompt_bindings += (
        SimpleNamespace(
            stage_key="sufficiency",
            messages=(SimpleNamespace(content_template="充分性规则" * 120),),
        ),
    )
    over_budget = await CustomerServiceRetrieval(
        Repository(), Embedding(), Reranker()
    ).search(
        tenant_id="dev", question="能事后补证明吗？", gateway=Gateway(), bundle=bundle
    )
    assert over_budget.assembly.selected == ()


@pytest.mark.asyncio
async def test_duplicate_child_text_in_one_version_does_not_consume_rerank_topk() -> (
    None
):
    release_id = uuid4()
    parent_ids = (uuid4(), uuid4(), uuid4())
    first = Evidence(
        chunk_id=uuid4(),
        parent_id=parent_ids[0],
        knowledge_base_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        index_release_id=release_id,
        document_title="制度",
        version_no=1,
        content="同一条款",
        content_hash=sha256("同一条款".encode()).hexdigest(),
        score=0.9,
    )
    duplicate = first.model_copy(
        update={"chunk_id": uuid4(), "parent_id": parent_ids[1], "score": 0.8}
    )
    unique = first.model_copy(
        update={
            "chunk_id": uuid4(),
            "parent_id": parent_ids[2],
            "content": "唯一例外",
            "content_hash": sha256("唯一例外".encode()).hexdigest(),
            "score": 0.7,
        }
    )
    parents = tuple(
        ParentEvidence(
            parent_id=parent_id,
            knowledge_base_id=first.knowledge_base_id,
            document_id=first.document_id,
            document_version_id=first.document_version_id,
            index_release_id=release_id,
            document_title="制度",
            version_no=1,
            content=content,
            content_hash=sha256(content.encode()).hexdigest(),
            token_count=20,
        )
        for parent_id, content in (
            (parent_ids[0], "同一条款"),
            (parent_ids[2], "唯一例外"),
        )
    )

    class Repository:
        async def vector_search(self, **_kwargs):
            return first, duplicate, unique

        async def fts_search(self, **_kwargs):
            return ()

        async def get_parents(self, **_kwargs):
            return parents

    class Gateway:
        async def complete(self, *_args):
            return QueryRewrite(queries=("条款和例外",))

    class Embedding:
        async def embed(self, _queries):
            return ((0.0,) * 1024,)

    class Reranker:
        async def rerank(self, _query, documents, *, top_n):
            assert documents == ("同一条款", "唯一例外")
            assert top_n == 2
            return ((0, 0.9), (1, 0.8))

    bundle = SimpleNamespace(
        rag_policy=SimpleNamespace(
            rewrite_query_limit=1,
            vector_top_k=3,
            fts_top_k=3,
            fusion_top_k=3,
            rerank_top_k=2,
            context_token_limit=1000,
        ),
        model_policy=SimpleNamespace(max_input_tokens=1000, max_output_tokens=100),
        prompt_bindings=(),
        knowledge_bindings=(SimpleNamespace(index_release_id=release_id),),
    )

    trace = await CustomerServiceRetrieval(
        Repository(), Embedding(), Reranker()
    ).search(tenant_id="dev", question="条款和例外？", gateway=Gateway(), bundle=bundle)

    assert len(trace.vector_candidates) == 3
    assert len(trace.fused_candidates) == 2
    assert len(trace.assembly.selected) == 2
