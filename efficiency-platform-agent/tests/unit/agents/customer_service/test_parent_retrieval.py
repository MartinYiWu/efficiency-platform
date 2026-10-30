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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "planned",
    [
        ("部署要求", "费用要求"),
        ("部署要求", "部署要求", "费用要求"),
        ("部署要求", "部署要求"),
        ("部署要求",),
        None,
    ],
)
@pytest.mark.parametrize("shared_head", [False, True])
async def test_planned_subqueries_share_bounded_rerank_slots(
    planned, shared_head
) -> None:
    release_id = uuid4()
    items = tuple(
        Evidence(
            chunk_id=uuid4(),
            knowledge_base_id=uuid4(),
            document_id=uuid4(),
            document_version_id=uuid4(),
            index_release_id=release_id,
            document_title="制度",
            version_no=1,
            content=text,
            content_hash=sha256(text.encode()).hexdigest(),
            score=0.8,
        )
        for text in ("部署规则甲", "部署规则乙", "费用预警", "额度暂停规则")
    )
    calls = []

    class Ports:
        async def vector_search(self, **kwargs):
            return items

        async def fts_search(self, **kwargs):
            return ()

        async def embed(self, queries):
            return tuple((0.0,) * 1024 for _ in queries)

        async def complete(self, *_args):
            assert planned is None
            return QueryRewrite(queries=("部署要求", "费用要求"))

        async def rerank(self, query, documents, *, top_n):
            calls.append(query)
            assert top_n == 3
            assert len(documents) == 4
            indexes = (
                ((0, 2, 3) if shared_head else (2, 0, 3))
                if query == "费用要求"
                else (0, 1, 2)
            )
            return tuple((i, 0.9 - rank * 0.1) for rank, i in enumerate(indexes))

    ports = Ports()
    bundle = SimpleNamespace(
        rag_policy=SimpleNamespace(
            rewrite_query_limit=3,
            vector_top_k=4,
            fts_top_k=4,
            fusion_top_k=4,
            rerank_top_k=3,
        ),
        knowledge_bindings=(SimpleNamespace(index_release_id=release_id),),
    )
    trace = await CustomerServiceRetrieval(ports, ports, ports).search(
        tenant_id="dev",
        question="部署及费用要求",
        gateway=ports,
        bundle=bundle,
        planned_queries=planned,
    )
    if planned and len(set(planned)) > 1:
        assert calls == ["部署要求", "费用要求"]
        expected = (
            ("部署规则甲", "部署规则乙", "费用预警")
            if shared_head
            else ("部署规则甲", "费用预警", "部署规则乙")
        )
    else:
        assert calls == ["部署及费用要求"]
        expected = ("部署规则甲", "部署规则乙", "费用预警")
    assert tuple(x.content for x in trace.reranked_evidence) == expected
    assert len({x.chunk_id for x in trace.reranked_evidence}) == 3


@pytest.mark.asyncio
async def test_planned_query_rerank_provider_failure_is_not_empty_evidence() -> None:
    release_id = uuid4()
    item = Evidence(
        chunk_id=uuid4(),
        knowledge_base_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        index_release_id=release_id,
        document_title="制度",
        version_no=1,
        content="依据",
        content_hash=sha256("依据".encode()).hexdigest(),
        score=0.8,
    )

    class Ports:
        async def vector_search(self, **kwargs):
            return (item,)

        async def fts_search(self, **kwargs):
            return ()

        async def embed(self, queries):
            return tuple((0.0,) * 1024 for _ in queries)

        async def rerank(self, query, documents, *, top_n):
            if query == "第二子问题":
                raise RuntimeError("PROVIDER_TIMEOUT")
            return ((0, 0.9),)

    ports = Ports()
    bundle = SimpleNamespace(
        rag_policy=SimpleNamespace(
            rewrite_query_limit=2,
            vector_top_k=4,
            fts_top_k=4,
            fusion_top_k=4,
            rerank_top_k=3,
        ),
        knowledge_bindings=(SimpleNamespace(index_release_id=release_id),),
    )
    with pytest.raises(RuntimeError, match="PROVIDER_TIMEOUT"):
        await CustomerServiceRetrieval(ports, ports, ports).search(
            tenant_id="dev",
            question="综合问题",
            gateway=ports,
            bundle=bundle,
            planned_queries=("第一子问题", "第二子问题"),
        )
