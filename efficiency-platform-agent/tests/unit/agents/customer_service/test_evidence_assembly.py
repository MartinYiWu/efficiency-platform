"""父片段证据装配契约。"""

from __future__ import annotations

from hashlib import sha256
from uuid import uuid4

import pytest

from efficiency_platform_agent.agents.customer_service.evidence_assembly import (
    assemble_evidence,
)
from efficiency_platform_agent.agents.customer_service.state import (
    Evidence,
    ParentEvidence,
)


def _evidence(*, parent_id, content: str, score: float) -> Evidence:
    return Evidence(
        chunk_id=uuid4(),
        parent_id=parent_id,
        knowledge_base_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        index_release_id=uuid4(),
        document_title="公司制度",
        version_no=1,
        content=content,
        content_hash=sha256(content.encode()).hexdigest(),
        score=score,
    )


def test_same_parent_is_sent_once_and_never_truncated() -> None:
    parent_id = uuid4()
    original = "第一条 员工申请。紧急情况允许事后补交证明。"
    first = _evidence(parent_id=parent_id, content="员工申请", score=0.9)
    second = first.model_copy(
        update={"chunk_id": uuid4(), "content": "事后补交", "score": 0.8}
    )
    parent = ParentEvidence(
        parent_id=parent_id,
        knowledge_base_id=first.knowledge_base_id,
        document_id=first.document_id,
        document_version_id=first.document_version_id,
        index_release_id=first.index_release_id,
        document_title="公司制度",
        version_no=1,
        content=original,
        content_hash=sha256(original.encode()).hexdigest(),
        token_count=28,
    )

    result = assemble_evidence(
        (first, second), (parent,), context_token_limit=100, reserved_tokens=20
    )

    assert len(result.selected) == 1
    assert result.selected[0].content == original
    assert result.selected[0].chunk_id == first.chunk_id
    assert result.selected[0].parent_id == parent_id
    assert result.hit_chunk_ids[parent_id] == (first.chunk_id, second.chunk_id)


def test_budget_excludes_whole_parent() -> None:
    parent_id = uuid4()
    child = _evidence(parent_id=parent_id, content="申请", score=0.9)
    parent = ParentEvidence(
        parent_id=parent_id,
        knowledge_base_id=child.knowledge_base_id,
        document_id=child.document_id,
        document_version_id=child.document_version_id,
        index_release_id=child.index_release_id,
        document_title="公司制度",
        version_no=1,
        content="第一条 员工申请。紧急情况允许事后补交证明。",
        content_hash="a" * 64,
        token_count=50,
    )

    result = assemble_evidence(
        (child,), (parent,), context_token_limit=60, reserved_tokens=20
    )

    assert result.selected == ()
    assert result.excluded_parent_ids == (parent_id,)


def test_selected_evidence_keeps_hit_page_when_parent_spans_pages() -> None:
    parent_id = uuid4()
    child = _evidence(parent_id=parent_id, content="第二页条款", score=0.9)
    child = child.model_copy(update={"page_no": 2})
    parent = ParentEvidence(
        parent_id=parent_id,
        knowledge_base_id=child.knowledge_base_id,
        document_id=child.document_id,
        document_version_id=child.document_version_id,
        index_release_id=child.index_release_id,
        document_title="跨页制度",
        version_no=1,
        page_no=1,
        page_end=2,
        content="第一页前提。第二页条款",
        content_hash="a" * 64,
        token_count=30,
    )

    result = assemble_evidence(
        (child,), (parent,), context_token_limit=100, reserved_tokens=10
    )

    assert result.selected[0].page_no == 2
    assert result.selected_parents[0].page_end == 2


def test_exact_duplicate_parent_does_not_consume_budget_for_unique_clause() -> None:
    parent_ids = (uuid4(), uuid4(), uuid4())
    texts = ("完整相同条款", "完整相同条款", "唯一有效例外")
    first = _evidence(parent_id=parent_ids[0], content="条款", score=0.9)
    children = tuple(
        first.model_copy(
            update={
                "chunk_id": uuid4(),
                "parent_id": parent_id,
                "score": 0.9 - index * 0.1,
            }
        )
        for index, parent_id in enumerate(parent_ids)
    )
    parents = tuple(
        ParentEvidence(
            parent_id=parent_id,
            knowledge_base_id=first.knowledge_base_id,
            document_id=first.document_id,
            document_version_id=first.document_version_id,
            index_release_id=first.index_release_id,
            document_title="制度",
            version_no=1,
            content=content,
            content_hash=sha256(content.encode()).hexdigest(),
            token_count=30,
        )
        for parent_id, content in zip(parent_ids, texts, strict=True)
    )

    result = assemble_evidence(
        children, parents, context_token_limit=80, reserved_tokens=20
    )

    assert tuple(item.parent_id for item in result.selected) == (
        parent_ids[0],
        parent_ids[2],
    )
    assert result.duplicate_parent_ids == (parent_ids[1],)
    assert result.excluded_parent_ids == ()
    assert len(result.hit_chunk_ids) == 3


def group_fixture(kind="PARAGRAPH", table_id=None):
    first = _evidence(parent_id=uuid4(), content="甲", score=0.9)
    children = tuple(
        first.model_copy(update={"chunk_id": uuid4(), "parent_id": uuid4()})
        for _ in range(4)
    )
    parents = tuple(
        ParentEvidence.model_validate(
            {
                **{
                    k: v
                    for k, v in child.model_dump().items()
                    if k in ParentEvidence.model_fields
                },
                "content": f"完整原文{i}",
                "token_count": 20,
                "parent_no": i + 1,
                "block_kind": kind,
                "source_table_id": table_id,
            }
        )
        for i, child in enumerate(children)
    )
    return children, parents


def test_final_topk_counts_independent_parents_before_budget():
    children, parents = group_fixture()
    result = assemble_evidence(
        children,
        parents,
        context_token_limit=30,
        reserved_tokens=0,
        final_evidence_top_k=3,
        adjacent_group_max_parents=2,
    )
    assert len(result.candidate_parents) == 3
    assert result.groups[0].parent_ids == tuple(p.parent_id for p in parents[:2])
    assert len(result.selected) == 1
    assert result.exclusion_reasons[parents[1].parent_id] == "BUDGET_EXCLUDED"
    assert result.exclusion_reasons[parents[3].parent_id] == "FINAL_TOP_K_EXCLUDED"


@pytest.mark.parametrize("kind", ["NUMBERED_RULE", "LIST", "CODE", "TABLE"])
def test_protected_or_unidentified_blocks_do_not_group(kind):
    children, parents = group_fixture(kind)
    result = assemble_evidence(
        children,
        parents,
        context_token_limit=100,
        reserved_tokens=0,
        final_evidence_top_k=4,
        adjacent_group_max_parents=3,
    )
    assert result.groups == ()
    if kind == "TABLE":
        assert (
            result.grouping_reasons[parents[0].parent_id]
            == "TABLE_IDENTITY_UNAVAILABLE"
        )


def test_table_groups_require_same_frozen_source_and_consecutive_parent_numbers():
    children, parents = group_fixture("TABLE", 0)
    parents = parents[:2] + (
        parents[2].model_copy(update={"source_table_id": 100}),
        parents[3].model_copy(update={"parent_no": 8}),
    )
    result = assemble_evidence(
        children,
        parents,
        context_token_limit=100,
        reserved_tokens=0,
        final_evidence_top_k=4,
        adjacent_group_max_parents=3,
    )
    assert [g.parent_ids for g in result.groups] == [
        tuple(p.parent_id for p in parents[:2])
    ]


def test_split_tables_freeze_source_identity_without_using_repeated_headers():
    from efficiency_platform_agent.agents.customer_service.chunking import (
        parent_child_document,
    )
    from efficiency_platform_agent.agents.customer_service.contracts import (
        ParsedDocument,
    )

    table = "| 名 | 值 |\n| --- | --- |\n" + "\n".join(
        f"| 项{i} | 数值{i} |" for i in range(8)
    )
    document = ParsedDocument(markdown=table + "\n\n" + table)
    parents = parent_child_document(
        document, parent_max_tokens=40, child_max_tokens=20, child_overlap_tokens=0
    )
    ids = [p.source_table_id for p in parents]
    assert ids[0] == 0
    assert ids[-1] == len(table) + 2
    assert len(set(ids)) == 2
    assert all(p.block_kind == "TABLE" for p in parents)
    assert [p.parent_no for p in parents] == list(range(1, len(parents) + 1))


@pytest.mark.parametrize(
    "field,value",
    [
        ("section_path", "其他标题"),
        ("parent_no", 8),
        ("document_version_id", None),
        ("block_kind", "CODE"),
    ],
)
def test_adjacent_groups_respect_source_boundaries(field, value):
    children, parents = group_fixture()
    if field == "document_version_id":
        value = uuid4()
        children = (children[0], children[1].model_copy(update={field: value}))
    parents = (parents[0], parents[1].model_copy(update={field: value}))
    result = assemble_evidence(
        children[:2],
        parents,
        context_token_limit=100,
        reserved_tokens=0,
        final_evidence_top_k=2,
        adjacent_group_max_parents=3,
    )
    assert result.groups == ()


def test_group_presentation_uses_parent_order_without_synthetic_citation():
    children, parents = group_fixture()
    result = assemble_evidence(
        (children[1], children[0]),
        parents,
        context_token_limit=100,
        reserved_tokens=0,
        final_evidence_top_k=2,
        adjacent_group_max_parents=3,
    )
    assert [x.parent_id for x in result.selected] == [
        parents[0].parent_id,
        parents[1].parent_id,
    ]
    assert {x.chunk_id for x in result.selected} == {
        children[0].chunk_id,
        children[1].chunk_id,
    }
    result = assemble_evidence(
        (children[0], children[2]),
        parents,
        context_token_limit=100,
        reserved_tokens=0,
        final_evidence_top_k=2,
        adjacent_group_max_parents=3,
    )
    assert result.groups == ()
