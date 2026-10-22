"""相似候选只在受控核验后合并。"""

from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest

from efficiency_platform_agent.agents.customer_service.model_gateway import (
    StructuredModelError,
)
from efficiency_platform_agent.agents.customer_service.retrieval import (
    CustomerServiceRetrieval,
)
from efficiency_platform_agent.agents.customer_service.service import (
    CustomerServiceRunService,
)
from efficiency_platform_agent.agents.customer_service.state import (
    Evidence,
    ParentEvidence,
    QueryRewrite,
)


@pytest.mark.asyncio
async def test_legacy_release_preserves_original_rrf_semantics():
    s = Scenario()
    s.bundle.contract_version = "customer-service-release/1"
    s.bundle.rag_policy.fusion_top_k = 1
    duplicate = s.left.model_copy(update={"chunk_id": uuid4(), "parent_id": uuid4()})

    async def fts(**kwargs):
        return duplicate, s.right

    s.fts_search = fts
    trace = await s.search()
    assert trace.fused_candidates[0].chunk_id == s.right.chunk_id
    assert trace.fused_candidates[0].score == pytest.approx(2 / 62)


@pytest.mark.asyncio
async def test_invalid_child_hash_fails_before_equivalence():
    s = Scenario()
    s.items = (s.left.model_copy(update={"content_hash": "0" * 64}), s.right)
    original = s.get_parents

    async def parents(**kwargs):
        return tuple(
            p.model_copy(
                update={"content_hash": sha256(p.content.encode()).hexdigest()}
            )
            for p in await original(**kwargs)
        )

    s.get_parents = parents
    with pytest.raises(ValueError, match="CHILD_CONTENT_HASH_INVALID"):
        await s.search()
    assert "equivalence" not in s.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("start,end", [(0, 999), (None, 3)])
async def test_invalid_parent_offsets_fail_closed(start, end):
    s = Scenario()
    s.items = (
        s.left.model_copy(update={"hit_start_offset": start, "hit_end_offset": end}),
        s.right,
    )
    with pytest.raises(ValueError, match="PARENT_CHILD_OFFSET_INVALID"):
        await s.search()


class Scenario:
    def __init__(self):
        self.left = Evidence(
            chunk_id=uuid4(),
            parent_id=uuid4(),
            knowledge_base_id=uuid4(),
            document_id=uuid4(),
            document_version_id=uuid4(),
            index_release_id=uuid4(),
            document_title="制度",
            version_no=1,
            section_path="请假",
            content="须申请",
            content_hash=sha256("须申请".encode()).hexdigest(),
            score=0.8,
        )
        self.right = self.left.model_copy(
            update={
                "chunk_id": uuid4(),
                "parent_id": uuid4(),
                "content": "需要申请",
                "content_hash": sha256("需要申请".encode()).hexdigest(),
            }
        )
        self.items = (self.left, self.right)
        self.members = tuple(
            (
                x.knowledge_base_id,
                x.document_id,
                x.document_version_id,
                x.index_release_id,
            )
            for x in self.items
        )
        self.calls = []
        self.verdict = "EQUIVALENT"
        self.conditions = []
        self.invalid_quote = False
        self.error = None
        self.bundle = SimpleNamespace(
            contract_version="customer-service-release/2",
            rag_policy=SimpleNamespace(
                rewrite_query_limit=1,
                vector_top_k=5,
                fts_top_k=5,
                fusion_top_k=5,
                rerank_top_k=5,
                context_token_limit=4000,
                similarity_candidate_threshold=0.96,
                similarity_pair_limit=20,
            ),
            model_policy=SimpleNamespace(max_input_tokens=4000, max_output_tokens=100),
            prompt_bindings=(SimpleNamespace(stage_key="equivalence", messages=()),),
            knowledge_bindings=(
                SimpleNamespace(
                    index_release_id=self.left.index_release_id,
                    knowledge_base_id=self.left.knowledge_base_id,
                ),
            ),
        )

    async def get_index_members(self, **kwargs):
        self.calls.append("members")
        return self.members

    async def vector_search(self, **kwargs):
        return self.items

    async def fts_search(self, **kwargs):
        return ()

    async def get_chunk_vectors(self, **kwargs):
        self.calls.append("vectors")
        assert kwargs["index_release_ids"] == tuple(
            b.index_release_id for b in self.bundle.knowledge_bindings
        )
        return {x.chunk_id: (1.0, 0.0) for x in self.items}

    async def get_parents(self, **kwargs):
        self.calls.append("parents")
        return tuple(
            ParentEvidence(
                **x.model_dump(
                    exclude={
                        "chunk_id",
                        "score",
                        "hit_content",
                        "hit_content_hash",
                        "hit_start_offset",
                        "hit_end_offset",
                        "rank",
                        "query_index",
                    }
                ),
                token_count=20,
            )
            for x in self.items
            if x.parent_id in kwargs["parent_ids"]
        )

    async def embed(self, queries):
        self.calls.append("embed")
        return ((1.0,) * 1024,)

    async def rerank(self, query, documents, *, top_n):
        self.calls.append("rerank")
        return tuple((i, 0.9 - i * 0.1) for i in range(top_n))

    async def complete(self, stage, value, output_type):
        self.calls.append(stage)
        if stage == "rewrite":
            return QueryRewrite(queries=("请假",))
        assert stage == "equivalence"
        assert self.calls.index("parents") < self.calls.index("equivalence")
        if self.error:
            raise self.error
        return output_type.model_validate(
            {
                "left_chunk_id": value["left"]["chunk_id"],
                "right_chunk_id": value["right"]["chunk_id"],
                "verdict": self.verdict,
                "left_quote": "不存在"
                if self.invalid_quote
                else value["left"]["content"],
                "right_quote": value["right"]["content"],
                "differing_conditions": self.conditions,
            }
        )

    async def search(self):
        return await CustomerServiceRetrieval(self, self, self).search(
            tenant_id="test", question="如何请假？", gateway=self, bundle=self.bundle
        )


@pytest.mark.asyncio
async def test_verified_equivalence_and_event_facts():
    s = Scenario()
    trace = await s.search()
    assert len(trace.assembly.selected) == 1
    assert len(trace.reranked_evidence) == 2
    assert s.calls.count("embed") == 1
    facts = CustomerServiceRunService._retrieval_facts(
        SimpleNamespace(retrieval_trace=trace, sufficiency=None)
    )
    decision = facts["equivalence_decisions"][0]
    assert decision["merged_chunk_ids"] == [str(s.right.chunk_id)]
    assert decision["reason"] == "VERIFIED_EQUIVALENT"
    assert decision["right"]["document_version_id"] == str(s.right.document_version_id)
    assert facts["vector_candidates"][0]["rank"] == 1
    assert facts["fused_candidates"][0]["rank"] == 1
    assert facts["child_hits"][0]["rank"] == 1
    assert facts["child_hits"][0]["score"] == 0.9


@pytest.mark.asyncio
async def test_equivalence_event_freezes_both_original_parents_for_replay():
    from efficiency_platform_agent.agents.customer_service.state import (
        RunEvent,
        RunEventPayload,
        RunStatus,
    )

    s = Scenario()
    original = s.get_parents

    async def parents(**kwargs):
        return tuple(
            p.model_copy(
                update={
                    "content": p.content + "。紧急情况除外。",
                    "content_hash": sha256(
                        (p.content + "。紧急情况除外。").encode()
                    ).hexdigest(),
                }
            )
            for p in await original(**kwargs)
        )

    s.get_parents = parents
    trace = await s.search()
    facts = CustomerServiceRunService._retrieval_facts(
        SimpleNamespace(retrieval_trace=trace, sufficiency=None)
    )
    event = RunEvent(
        run_id=uuid4(),
        sequence=1,
        event_type="stage.completed",
        status=RunStatus.RUNNING,
        payload=RunEventPayload(retrieval_facts=facts),
    )
    frozen = RunEvent.model_validate_json(
        event.model_dump_json()
    ).payload.retrieval_facts
    decision = frozen["equivalence_decisions"][0]
    assert decision["left_parent"]["content"] == "须申请。紧急情况除外。"
    assert decision["right_parent"]["content"] == "需要申请。紧急情况除外。"
    assert (
        decision["right_parent"]["content_hash"]
        == sha256("需要申请。紧急情况除外。".encode()).hexdigest()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "condition,left,right",
    [
        ("否定", "允许补交证明", "不允许补交证明"),
        ("数字", "最多请假三天", "最多请假五天"),
        ("时间", "2026 年起执行", "2027 年起执行"),
        ("对象", "正式员工适用", "实习员工适用"),
        ("前提", "经审批可以请假", "无需审批可以请假"),
        ("例外", "节假日除外", "节假日同样适用"),
    ],
)
async def test_differing_conditions_prevent_merge(condition, left, right):
    s = Scenario()
    s.items = tuple(
        item.model_copy(
            update={
                "content": content,
                "content_hash": sha256(content.encode()).hexdigest(),
            }
        )
        for item, content in ((s.left, left), (s.right, right))
    )
    s.conditions = [condition]
    trace = await s.search()
    assert len(trace.assembly.selected) == 2
    assert trace.equivalence_decisions[0].reason == "DIFFERING_CONDITIONS"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,code",
    [
        ("quote", "EQUIVALENCE_QUOTE_INVALID"),
        ("stage", "PROMPT_STAGE_NOT_BOUND"),
        ("provider", "PROVIDER_TIMEOUT"),
        ("uncertain", "UNCERTAIN"),
    ],
)
async def test_failed_or_uncertain_equivalence_retains_both(mode, code):
    s = Scenario()
    s.invalid_quote = mode == "quote"
    if mode == "stage":
        s.bundle.prompt_bindings = ()
    if mode == "provider":
        s.error = StructuredModelError(code, "超时")
    if mode == "uncertain":
        s.verdict = "UNCERTAIN"
    trace = await s.search()
    assert len(trace.assembly.selected) == 2
    assert trace.equivalence_decisions[0].reason == code


@pytest.mark.asyncio
async def test_legacy_release_skips_new_stages():
    s = Scenario()
    s.bundle.contract_version = "customer-service-release/1"
    s.bundle.prompt_bindings = ()
    trace = await s.search()
    assert len(trace.assembly.selected) == 2
    assert not {"members", "vectors", "equivalence"}.intersection(s.calls)


@pytest.mark.asyncio
async def test_old_index_candidates_are_excluded_before_rrf():
    s = Scenario()
    s.items = (s.left.model_copy(update={"index_release_id": uuid4()}), s.right)
    trace = await s.search()
    assert [x.chunk_id for x in trace.fused_candidates] == [s.right.chunk_id]
    assert len(trace.version_exclusions) == 1
    facts = CustomerServiceRunService._retrieval_facts(
        SimpleNamespace(retrieval_trace=trace, sufficiency=None)
    )
    assert facts["version_exclusions"][0]["reason"] == "NOT_BOUND_INDEX_MEMBER"
    assert facts["version_exclusions"][0]["knowledge_base_id"] == str(
        s.left.knowledge_base_id
    )


@pytest.mark.asyncio
async def test_same_index_document_with_two_versions_is_rejected_before_search():
    s = Scenario()
    s.members += (
        (
            s.left.knowledge_base_id,
            s.left.document_id,
            uuid4(),
            s.left.index_release_id,
        ),
    )
    with pytest.raises(ValueError, match="INDEX_DOCUMENT_VERSION_CONFLICT") as failure:
        await s.search()
    assert failure.value.code == "INDEX_DOCUMENT_VERSION_CONFLICT"


@pytest.mark.asyncio
async def test_same_parent_children_are_not_compared():
    s = Scenario()
    s.items = (s.left, s.right.model_copy(update={"parent_id": s.left.parent_id}))
    trace = await s.search()
    assert "equivalence" not in s.calls
    assert trace.equivalence_decisions == ()


@pytest.mark.asyncio
async def test_rerank_error_remains_failure():
    s = Scenario()

    async def fail(*args, **kwargs):
        raise StructuredModelError("RERANK_TIMEOUT", "重排超时")

    s.rerank = fail
    with pytest.raises(StructuredModelError, match="重排超时"):
        await s.search()


@pytest.mark.asyncio
async def test_repository_reads_bound_members_and_existing_vectors():
    from pgvector import Vector

    from efficiency_platform_agent.agents.customer_service.vector_repository import (
        DocumentChunkRepository,
    )

    s = Scenario()
    statements = []

    class Connection:
        async def execute(self, sql, params):
            statements.append((sql, params))
            if "embedding" in sql:
                return [(str(s.left.chunk_id), Vector([1.0, 0.0]))]
            return [tuple(str(v) for v in s.members[0])]

    repository = DocumentChunkRepository(Connection())
    assert await repository.get_index_members(
        index_release_ids=(s.left.index_release_id,)
    ) == (s.members[0],)
    vectors = await repository.get_chunk_vectors(
        tenant_id="tenant",
        index_release_ids=(s.left.index_release_id,),
        chunk_ids=(s.left.chunk_id,),
    )
    assert vectors == {s.left.chunk_id: (1.0, 0.0)}
    assert "m.index_release_id=ANY" in statements[1][0]
    assert "c.tenant_id=%s" in statements[1][0]
    assert statements[1][1] == (
        "tenant",
        [str(s.left.index_release_id)],
        [str(s.left.chunk_id)],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ["knowledge_base_id", "document_id", "document_version_id", "section_path"]
)
async def test_cross_scope_never_compared(field):
    s = Scenario()
    right = s.right.model_copy(
        update={field: "另一标题" if field == "section_path" else uuid4()}
    )
    s.items = (s.left, right)
    if field == "knowledge_base_id":
        s.bundle.knowledge_bindings += (
            SimpleNamespace(
                knowledge_base_id=right.knowledge_base_id,
                index_release_id=right.index_release_id,
            ),
        )
    if field == "document_version_id":
        right = right.model_copy(update={"document_id": uuid4()})
        s.items = (s.left, right)
    s.members = tuple(
        (x.knowledge_base_id, x.document_id, x.document_version_id, x.index_release_id)
        for x in s.items
    )
    trace = await s.search()
    assert len(trace.assembly.selected) == 2
    assert "equivalence" not in s.calls


@pytest.mark.asyncio
async def test_invalid_id_and_schema_keep_both():
    s = Scenario()
    original = s.complete

    async def bad_id(stage, value, output_type):
        result = await original(stage, value, output_type)
        return (
            result.model_copy(update={"left_chunk_id": uuid4()})
            if stage == "equivalence"
            else result
        )

    s.complete = bad_id
    trace = await s.search()
    assert len(trace.assembly.selected) == 2
    assert trace.equivalence_decisions[0].reason == "EQUIVALENCE_ID_INVALID"

    async def bad_schema(stage, value, output_type):
        if stage == "equivalence":
            return output_type.model_validate({})
        return await original(stage, value, output_type)

    s.complete = bad_schema
    trace = await s.search()
    assert len(trace.assembly.selected) == 2
    assert trace.equivalence_decisions[0].reason == "EQUIVALENCE_CONTRACT_INVALID"


@pytest.mark.asyncio
async def test_similarity_priority_pair_limit_and_nontransitive_grouping():
    s = Scenario()
    third = s.right.model_copy(
        update={
            "chunk_id": uuid4(),
            "parent_id": uuid4(),
            "content": "请先申请",
            "content_hash": sha256("请先申请".encode()).hexdigest(),
        }
    )
    s.items += (third,)
    s.bundle.rag_policy.similarity_pair_limit = 1

    async def vectors(**kwargs):
        return {
            s.left.chunk_id: (1.0, 0.1),
            s.right.chunk_id: (1.0, 0.0),
            third.chunk_id: (1.0, 0.0),
        }

    s.get_chunk_vectors = vectors
    trace = await s.search()
    assert len(trace.equivalence_decisions) == 1
    assert {
        trace.equivalence_decisions[0].left.chunk_id,
        trace.equivalence_decisions[0].right.chunk_id,
    } == {s.right.chunk_id, third.chunk_id}
    assert len(trace.assembly.selected) == 2


@pytest.mark.asyncio
async def test_stored_vector_failure_preserves_candidates_with_code():
    s = Scenario()

    async def vectors(**kwargs):
        raise StructuredModelError("STORED_VECTOR_UNAVAILABLE", "不可用")

    s.get_chunk_vectors = vectors
    trace = await s.search()
    assert len(trace.assembly.selected) == 2
    facts = CustomerServiceRunService._retrieval_facts(
        SimpleNamespace(retrieval_trace=trace, sufficiency=None)
    )
    assert facts["equivalence_errors"] == ["STORED_VECTOR_UNAVAILABLE"]


@pytest.mark.asyncio
async def test_exact_child_duplicates_share_rrf_votes_before_fusion():
    s = Scenario()
    duplicate = s.left.model_copy(update={"chunk_id": uuid4(), "parent_id": uuid4()})
    s.items = (s.left, s.right)

    async def fts(**kwargs):
        return duplicate, s.right

    s.fts_search = fts
    trace = await s.search()
    assert trace.fused_candidates[0].chunk_id == s.left.chunk_id
    assert trace.fused_candidates[0].score == pytest.approx(2 / 61)


@pytest.mark.asyncio
async def test_recall_ranks_restart_for_each_rewritten_query_in_frozen_facts():
    s = Scenario()
    s.bundle.rag_policy.rewrite_query_limit = 2
    original = s.complete

    async def complete(stage, value, output_type):
        if stage == "rewrite":
            return QueryRewrite(queries=("请假", "申请"))
        return await original(stage, value, output_type)

    async def embed(queries):
        return ((1.0,) * 1024,) * 2

    s.complete = complete
    s.embed = embed
    trace = await s.search()
    facts = CustomerServiceRunService._retrieval_facts(
        SimpleNamespace(retrieval_trace=trace, sufficiency=None)
    )
    assert [x["rank"] for x in facts["vector_candidates"]] == [1, 2, 1, 2]
    assert [x["query_index"] for x in facts["vector_candidates"]] == [1, 1, 2, 2]
    assert trace.vector_candidates[2].model_dump(mode="json")["rank"] == 1


@pytest.mark.asyncio
async def test_unexpected_prompt_failure_keeps_pair_and_prior_decisions():
    s = Scenario()
    s.error = TimeoutError("不可输出的故障详情")
    trace = await s.search()
    assert len(trace.assembly.selected) == 2
    assert trace.equivalence_decisions[0].reason == "TimeoutError"


@pytest.mark.asyncio
async def test_nontransitive_equivalence_keeps_unverified_third_parent():
    s = Scenario()
    third = s.right.model_copy(
        update={
            "chunk_id": uuid4(),
            "parent_id": uuid4(),
            "content": "申请即可",
            "content_hash": sha256("申请即可".encode()).hexdigest(),
        }
    )
    s.items += (third,)
    original = s.complete

    async def complete(stage, value, output_type):
        result = await original(stage, value, output_type)
        if stage == "equivalence" and {
            value["left"]["chunk_id"],
            value["right"]["chunk_id"],
        } == {str(s.left.chunk_id), str(third.chunk_id)}:
            return result.model_copy(update={"verdict": "DIFFERENT"})
        return result

    s.complete = complete
    trace = await s.search()
    assert {x.parent_id for x in trace.assembly.selected} == {
        s.left.parent_id,
        third.parent_id,
    }
