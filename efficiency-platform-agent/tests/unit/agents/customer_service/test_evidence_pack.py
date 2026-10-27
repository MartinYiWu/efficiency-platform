"""冻结证据包、预算、模型切换与引用闭包。"""

from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest

from efficiency_platform_agent.agents.customer_service.chunking import count_tokens
from efficiency_platform_agent.agents.customer_service.conflict_screen import (
    ConflictPair,
    ConflictScreen,
)
from efficiency_platform_agent.agents.customer_service.evidence_assembly import (
    assemble_evidence,
    build_evidence_pack,
)
from efficiency_platform_agent.agents.customer_service.release_bundle import (
    ModelPolicy,
    PromptBinding,
)
from efficiency_platform_agent.agents.customer_service.state import (
    Evidence,
    EvidencePack,
    ParentEvidence,
)


def bundle(limit=6000, large=None, padding=""):
    policy = ModelPolicy(
        policy_key="main",
        semantic_version="1",
        provider="fake",
        model_name="main",
        temperature=0,
        top_p=1,
        max_input_tokens=limit,
        max_output_tokens=100,
        connect_timeout_ms=100,
        read_timeout_ms=100,
        max_retries=0,
        checksum="a" * 64,
    )
    stages = (
        "safety",
        "identity",
        "citation",
        "general_advice",
        "sufficiency",
        "answer_company",
        "answer_mixed",
        "answer_repair",
        "evidence_extract",
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
                    "message_key": "s",
                    "content_template": padding
                    if stage == "sufficiency" and padding
                    else "遵守契约",
                    "content_format": "TEXT",
                    "trusted_instruction": True,
                    "checksum": "a" * 64,
                    "variables": (),
                },
                {
                    "ordinal": 2,
                    "role": "USER",
                    "message_key": "u",
                    "content_template": "共享规则"
                    if stage in {"safety", "identity", "citation", "general_advice"}
                    else "{{input_json}}",
                    "content_format": "JSON",
                    "trusted_instruction": False,
                    "checksum": "a" * 64,
                    "variables": (),
                },
            ),
        )
        for stage in stages
    )
    return SimpleNamespace(
        contract_version="customer-service-release/2",
        model_policy=policy,
        large_context_model_policy=policy.model_copy(
            update={
                "policy_key": "large",
                "model_name": "large",
                "max_input_tokens": large,
            }
        )
        if large
        else None,
        rag_policy=SimpleNamespace(context_token_limit=50000, rewrite_query_limit=2),
        prompt_bindings=bindings,
    )


def assembly(text="完整条款。", mode="FULL_ONLY", kind="PARAGRAPH"):
    parent = ParentEvidence(
        parent_id=uuid4(),
        knowledge_base_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        index_release_id=uuid4(),
        document_title="资料",
        version_no=1,
        content=text,
        content_hash=sha256(text.encode()).hexdigest(),
        token_count=count_tokens(text),
        evidence_mode=mode,
        block_kind=kind,
    )
    child = Evidence(
        **{k: v for k, v in parent.model_dump().items() if k in Evidence.model_fields},
        chunk_id=uuid4(),
        score=0.9,
        rank=1,
        hit_start_offset=0,
        hit_end_offset=len(text),
    )
    return assemble_evidence(
        (child,),
        (parent,),
        context_token_limit=100000,
        reserved_tokens=0,
        final_evidence_top_k=8,
    )


class ExtractGateway:
    def __init__(self, ids=(1,)):
        self.calls = []
        self.ids = ids

    async def complete(self, stage, value, output_type):
        self.calls.append((stage, value))
        return output_type(
            parent_id=value["parent_id"],
            selected_sentence_ids=self.ids,
            reason="相关原句",
        )


async def build(source=None, config=None, gateway=None, **kwargs):
    return await build_evidence_pack(
        source or assembly(),
        bundle=config or bundle(),
        gateway=gateway or ExtractGateway(),
        question="问题",
        history=(),
        conflict_screen=None,
        **kwargs,
    )


@pytest.mark.parametrize("kind", ["NUMBERED_RULE", "LIST", "TABLE", "CODE"])
async def test_protected_blocks_never_extract(kind):
    gateway = ExtractGateway()
    pack = await build(
        assembly("完整条款。" * 2000, "EXTRACTIVE_NARRATIVE", kind), gateway=gateway
    )
    assert pack.entries == ()
    assert pack.blocked
    assert gateway.calls == []


async def test_bound_larger_model_rebudgets_complete_protected_parent():
    source = assembly("完整条款。" * 2000)
    pack = await build(source, bundle(large=30000))
    assert pack.model_policy.model_name == "large"
    assert pack.entries[0].content == source.candidate_parents[0].content
    assert pack.entries[0].citation_type == "FULL_PARENT"
    assert pack.budget.used_tokens <= pack.budget.context_token_limit
    assert EvidencePack.model_validate_json(pack.model_dump_json()) == pack
    with pytest.raises(ValueError):
        pack.entries[0].content = "篡改"


async def test_equal_or_unbound_alternative_never_switches():
    for config in (bundle(), bundle(large=6000)):
        pack = await build(assembly("完整条款。" * 2000), config)
        assert pack.model_policy.model_name == "main"
        assert pack.blocked


async def test_extraction_input_is_never_truncated():
    gateway = ExtractGateway()
    pack = await build(
        assembly("完整句段。" * 2000, "EXTRACTIVE_NARRATIVE"), gateway=gateway
    )
    assert not pack.entries
    assert gateway.calls == []
    assert "EXTRACTION_INPUT_TOO_LARGE" in [x.reason for x in pack.exclusions]


async def test_allowed_narrative_extracts_only_when_full_parent_does_not_fit():
    gateway = ExtractGateway(ids=(3,))
    source = assembly("第一句。" + "中" * 1500 + "。第三句。", "EXTRACTIVE_NARRATIVE")
    pack = await build(source, bundle(limit=8000, padding="模" * 5000), gateway)
    assert len(gateway.calls) == 1
    assert pack.entries[0].citation_type == "EXTRACTED_SPANS"
    assert pack.entries[0].content == "第三句。"
    assert pack.entries[0].original_parent == source.candidate_parents[0]
    assert pack.entries[0].original_spans[0].start_offset == 1505
    assert pack.extraction_decisions[0].reason == "相关原句"
    assert "相关原句" not in str(pack.model_input())


async def test_conflict_sides_are_atomic_when_budget_cannot_fit_both():
    left, right = assembly("甲。" * 1400), assembly("乙。" * 1400)
    source = replace(
        left,
        candidate_parents=left.candidate_parents + right.candidate_parents,
        selected=left.selected + right.selected,
        hit_chunk_ids=left.hit_chunk_ids | right.hit_chunk_ids,
    )
    conflict = ConflictScreen(
        pairs=(
            ConflictPair(
                left_parent_id=left.candidate_parents[0].parent_id,
                right_parent_id=right.candidate_parents[0].parent_id,
                same_scope=True,
                verdict="CONFLICT",
                left_quote="甲。",
                right_quote="乙。",
                reason="冲突",
            ),
        ),
        blocked=True,
    )
    pack = await build_evidence_pack(
        source,
        bundle=bundle(),
        gateway=ExtractGateway(),
        question="问题",
        history=(),
        conflict_screen=conflict,
    )
    assert pack.blocked
    assert pack.entries == ()
    assert len(pack.exclusions) == 2
    assert pack.conflict_screen == conflict


async def test_history_and_real_templates_reduce_available_budget():
    config = bundle()
    source = assembly()
    first = await build(source, config)
    from efficiency_platform_agent.agents.customer_service.state import HistoryMessage

    second = await build_evidence_pack(
        source,
        bundle=config,
        gateway=ExtractGateway(),
        question="问题",
        history=(HistoryMessage(role="user", content="历史" * 200),),
        conflict_screen=None,
    )
    assert second.budget.reserved_tokens > first.budget.reserved_tokens
    assert first.budget.reserved_tokens > config.model_policy.max_output_tokens + 256


def company_answer(chunk_id):
    from efficiency_platform_agent.agents.customer_service.state import (
        CustomerServiceAnswer,
    )

    return CustomerServiceAnswer(
        contract_version="customer-service-answer/1",
        answer_mode="COMPANY_KNOWLEDGE",
        company_sections=(
            {
                "title": "公司资料",
                "paragraphs": (
                    {"text": "有依据的事实", "supporting_chunk_ids": (chunk_id,)},
                ),
            },
        ),
    )


@pytest.mark.parametrize("extracted", [False, True])
async def test_full_and_extracted_citations_close_against_frozen_source(extracted):
    from efficiency_platform_agent.agents.customer_service.citations import (
        freeze_citations,
        validate_citation_closure,
    )
    from efficiency_platform_agent.agents.customer_service.renderer import render_answer

    source = (
        assembly("第一句。" + "中" * 1500 + "。第三句。", "EXTRACTIVE_NARRATIVE")
        if extracted
        else assembly()
    )
    pack = await build(
        source,
        bundle(limit=8000, padding="模" * 5000) if extracted else bundle(),
        ExtractGateway((3,)),
    )
    answer = company_answer(pack.entries[0].chunk_id)
    validate_citation_closure(answer, pack)
    citation = freeze_citations(answer, pack)[0]
    assert citation.quoted_text == pack.entries[0].content
    assert citation.original_spans == pack.entries[0].original_spans
    assert citation.content_hash == source.candidate_parents[0].content_hash
    assert ("原文节选" in render_answer(answer, pack).markdown) == extracted


@pytest.mark.parametrize(
    "update",
    [
        {"content": "被改写"},
        {"content_hash": "a" * 64},
        {"document_version_id": uuid4()},
        {"index_release_id": uuid4()},
    ],
)
async def test_forged_pack_cannot_generate_company_citations(update):
    from efficiency_platform_agent.agents.customer_service.citations import (
        CitationGuardError,
        validate_citation_closure,
    )

    pack = await build()
    forged = pack.model_copy(
        update={"entries": (pack.entries[0].model_copy(update=update),)}
    )
    with pytest.raises(CitationGuardError):
        validate_citation_closure(company_answer(pack.entries[0].chunk_id), forged)


async def test_mysql_snapshot_replays_pack_without_reassembly():
    import json

    from test_retrieval_snapshot_repository import RecordingEngine

    from efficiency_platform_agent.agents.customer_service.retrieval import (
        RetrievalTrace,
    )
    from efficiency_platform_agent.agents.customer_service.retrieval_snapshot_repository import (
        MySqlRetrievalSnapshotRepository,
    )
    from efficiency_platform_agent.agents.customer_service.state import (
        SufficiencyDecision,
    )

    pack = await build()
    trace = RetrievalTrace("问题", (), (), (), (), (), (), evidence_pack=pack)
    result = SimpleNamespace(
        retrieval_trace=trace,
        sufficiency=SufficiencyDecision(
            sufficient=False,
            supported_claims=(),
            unsupported_claims=(),
            conflicts=(),
            recommended_mode="INSUFFICIENT_EVIDENCE",
        ),
    )
    engine = RecordingEngine()
    await MySqlRetrievalSnapshotRepository(engine).save(uuid4(), result)
    saved = json.loads(engine.calls[0][1]["retrieval_facts"])
    assert EvidencePack.model_validate(saved["evidence_pack"]) == pack


async def test_graph_shares_one_pack_and_switches_both_model_stages():
    from efficiency_platform_agent.agents.customer_service.graph import (
        CustomerServiceGraph,
    )
    from efficiency_platform_agent.agents.customer_service.retrieval import (
        RetrievalTrace,
    )
    from efficiency_platform_agent.agents.customer_service.state import (
        CustomerServiceRunRequest,
    )

    source = assembly("完整条款。" * 2000)

    class Retrieval:
        async def search(self, **kwargs):
            return RetrievalTrace(
                "问题", (), (), (), (), (), source.selected, assembly=source
            )

    class Gateway:
        policy = "main"

        def __init__(self):
            self.calls = []

        def with_model_policy(self, policy):
            self.policy = policy.model_name
            return self

        async def complete(self, stage, value, output_type):
            self.calls.append((stage, self.policy, value))
            if stage == "intent":
                return output_type(
                    intent_type="COMPANY_QUERY",
                    requires_company_knowledge=True,
                    requires_general_advice=False,
                    normalized_question="问题",
                )
            if stage == "sufficiency":
                return output_type(
                    sufficient=True,
                    supported_claims=(),
                    unsupported_claims=(),
                    conflicts=(),
                    recommended_mode="COMPANY_KNOWLEDGE",
                )
            return company_answer(source.selected[0].chunk_id)

    gateway = Gateway()
    request = CustomerServiceRunRequest(
        contract_version="customer-service-run/1",
        request_id="r",
        conversation_id=uuid4(),
        tenant_id="t",
        user_id="u",
        agent_release_id=uuid4(),
        message="问题",
        history=(),
    )
    result = await CustomerServiceGraph(Retrieval()).run(
        request, bundle(large=30000), gateway
    )
    assert result.evidence_pack is result.retrieval_trace.evidence_pack
    relevant = [x for x in gateway.calls if x[0] in {"sufficiency", "answer_company"}]
    assert [x[1] for x in relevant] == ["large", "large"]
    assert (
        relevant[0][2]["evidence"]
        == relevant[1][2]["evidence"]
        == result.evidence_pack.model_input()
    )


@pytest.mark.parametrize("ids", [(), (99,), (2,)])
async def test_invalid_or_still_oversized_extraction_excludes_parent(ids):
    source = assembly("第一句。" + "中" * 3000 + "。第三句。", "EXTRACTIVE_NARRATIVE")
    gateway = ExtractGateway(ids)
    pack = await build(source, bundle(limit=8000, padding="模" * 5000), gateway)
    assert gateway.calls
    assert not pack.entries
    assert pack.exclusions


async def test_full_narrative_does_not_call_extractor():
    gateway = ExtractGateway()
    pack = await build(assembly("完整句子。", "EXTRACTIVE_NARRATIVE"), gateway=gateway)
    assert pack.entries[0].citation_type == "FULL_PARENT"
    assert not gateway.calls


async def test_larger_model_still_too_small_stops_company_answer():
    pack = await build(assembly("完整条款。" * 2000), bundle(large=7000))
    assert pack.blocked
    assert not pack.entries


async def test_legacy_release_does_not_enable_pack():
    config = bundle(large=30000)
    config.contract_version = "customer-service-release/1"
    with pytest.raises(ValueError, match="REQUIRES_RELEASE_V2"):
        await build(config=config)


async def test_real_gateway_refuses_oversize_without_provider_or_truncation():
    from efficiency_platform_agent.agents.customer_service.evidence_extract import (
        ExtractionSelection,
    )
    from efficiency_platform_agent.agents.customer_service.model_gateway import (
        ReleaseStructuredModelGateway,
        StructuredModelError,
    )

    class Provider:
        async def complete(self, request):
            pytest.fail("超预算不得调用 Provider")

    gateway = ReleaseStructuredModelGateway(Provider(), bundle())
    with pytest.raises(StructuredModelError, match="完整输入"):
        await gateway.complete(
            "evidence_extract", {"original": "原" * 10000}, ExtractionSelection
        )


def test_pure_prompt_budget_matches_messages_sent_to_provider():
    from efficiency_platform_agent.agents.customer_service import model_gateway
    from efficiency_platform_agent.agents.customer_service.state import (
        SufficiencyDecision,
    )

    counter = getattr(model_gateway, "prompt_input_tokens", None)
    assert callable(counter), "预算计数必须能在没有 Provider 时使用"

    class Provider:
        async def complete(self, request):
            pytest.fail("仅渲染和计数不得调用 Provider")

    config = bundle()
    value = {"question": "年假申请", "evidence": ["完整条款。"]}
    gateway = model_gateway.ReleaseStructuredModelGateway(Provider(), config)
    messages = gateway._request_messages("sufficiency", value, SufficiencyDecision)
    expected = sum(count_tokens(message.content) + 8 for message in messages)
    assert counter(config, "sufficiency", value, SufficiencyDecision) == expected
    assert gateway.input_tokens("sufficiency", value, SufficiencyDecision) == expected


async def test_pack_rejects_child_without_parent_identity():
    source = assembly()
    child = source.selected[0].model_copy(update={"parent_id": None})
    with pytest.raises(ValueError, match="PARENT_EVIDENCE_MISSING"):
        await build(source, children=(child,))


async def test_actual_intent_payload_is_included_in_answer_budget():
    from efficiency_platform_agent.agents.customer_service.state import IntentDecision

    intent = IntentDecision(
        intent_type="COMPANY_QUERY",
        requires_company_knowledge=True,
        requires_general_advice=False,
        normalized_question="问" * 4000,
    )
    pack = await build(intent=intent)
    baseline = await build()
    assert pack.budget.reserved_tokens >= baseline.budget.reserved_tokens + 4000


async def test_pack_preserves_group_presentation_and_rerank_order_metadata():
    from efficiency_platform_agent.agents.customer_service.state import EvidenceGroup

    first, second = assembly("第一段。"), assembly("第二段。")
    source = replace(
        first,
        candidate_parents=second.candidate_parents + first.candidate_parents,
        selected=second.selected + first.selected,
        hit_chunk_ids=first.hit_chunk_ids | second.hit_chunk_ids,
        groups=(
            EvidenceGroup(
                parent_ids=(
                    first.candidate_parents[0].parent_id,
                    second.candidate_parents[0].parent_id,
                )
            ),
        ),
    )
    pack = await build(source)
    assert tuple(e.parent_id for e in pack.entries) == source.groups[0].parent_ids


async def test_debug_selection_facts_follow_final_pack():
    from efficiency_platform_agent.agents.customer_service.retrieval import (
        RetrievalTrace,
    )
    from efficiency_platform_agent.agents.customer_service.retrieval_snapshot_repository import (
        evidence_processing_facts,
    )

    source = assembly("完整条款。" * 2000)
    pack = await build(source)
    trace = RetrievalTrace(
        "问题", (), (), (), (), (), (), assembly=source, evidence_pack=pack
    )
    facts = evidence_processing_facts(trace)
    assert facts["assembly_decisions"][0]["selected"] is False
    assert facts["assembly_decisions"][0]["reason"] == "BUDGET_EXCLUDED"


async def test_frozen_hit_offset_mismatch_is_rejected():
    from efficiency_platform_agent.agents.customer_service.citations import (
        CitationGuardError,
        validate_evidence_pack,
    )

    pack = await build()
    forged = pack.model_copy(
        update={"entries": (pack.entries[0].model_copy(update={"hit_end_offset": 1}),)}
    )
    with pytest.raises(CitationGuardError):
        validate_evidence_pack(forged)


async def test_v2_parentless_candidates_cannot_fall_back_to_legacy_company_answer():
    from efficiency_platform_agent.agents.customer_service.graph import (
        CustomerServiceGraph,
    )
    from efficiency_platform_agent.agents.customer_service.retrieval import (
        RetrievalTrace,
    )
    from efficiency_platform_agent.agents.customer_service.state import (
        CustomerServiceRunRequest,
    )

    source = assembly()

    class Retrieval:
        async def search(self, **kwargs):
            return RetrievalTrace(
                "问题", (), (), (), (), (), source.selected, assembly=None
            )

    class Gateway:
        async def complete(self, stage, value, output_type):
            if stage == "intent":
                return output_type(
                    intent_type="COMPANY_QUERY",
                    requires_company_knowledge=True,
                    requires_general_advice=False,
                    normalized_question="问题",
                )
            pytest.fail("无冻结父原文不得调用公司模型")

    request = CustomerServiceRunRequest(
        contract_version="customer-service-run/1",
        request_id="r",
        conversation_id=uuid4(),
        tenant_id="t",
        user_id="u",
        agent_release_id=uuid4(),
        message="问题",
        history=(),
    )
    result = await CustomerServiceGraph(Retrieval()).run(request, bundle(), Gateway())
    assert result.rendered.answer.answer_mode == "INSUFFICIENT_EVIDENCE"
    assert result.evidence_pack is not None


def test_legacy_citation_json_retains_legacy_shape():
    from efficiency_platform_agent.agents.customer_service.state import Citation

    citation = Citation(
        citation_no=1,
        knowledge_base_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        index_release_id=uuid4(),
        chunk_id=uuid4(),
        document_title="旧记录",
        version_no=1,
        section_path=None,
        page_no=None,
        quoted_text="原文",
        content_hash="a" * 64,
    )
    assert (
        not {"parent_id", "citation_type", "original_spans"}
        & citation.model_dump(mode="json").keys()
    )


async def test_final_runtime_budget_guard_returns_insufficient_without_repair():
    from efficiency_platform_agent.agents.customer_service.answer import generate_answer
    from efficiency_platform_agent.agents.customer_service.model_gateway import (
        StructuredModelError,
    )
    from efficiency_platform_agent.agents.customer_service.state import (
        IntentDecision,
        SufficiencyDecision,
    )
    from efficiency_platform_agent.agents.customer_service.sufficiency import (
        judge_sufficiency,
    )

    class Gateway:
        async def complete(self, stage, value, output_type):
            assert stage != "answer_repair"
            raise StructuredModelError(
                "MODEL_INPUT_BUDGET_EXCEEDED", "完整输入超过预算"
            )

    pack = await build()
    decision = await judge_sufficiency(Gateway(), "问题", pack)
    assert not decision.sufficient
    answer = await generate_answer(
        Gateway(),
        question="问题",
        intent=IntentDecision(
            intent_type="COMPANY_QUERY",
            requires_company_knowledge=True,
            requires_general_advice=False,
            normalized_question="问题",
        ),
        evidence=pack,
        sufficiency=SufficiencyDecision(
            sufficient=True,
            supported_claims=(),
            unsupported_claims=(),
            conflicts=(),
            recommended_mode="COMPANY_KNOWLEDGE",
        ),
    )
    assert answer.answer_mode == "INSUFFICIENT_EVIDENCE"


async def test_pack_uses_surviving_child_after_equivalence_filter():
    source = assembly()
    eliminated = source.selected[0].model_copy(update={"chunk_id": uuid4()})
    pack = await build(source, children=(eliminated, source.selected[0]))
    assert pack.entries[0].chunk_id == source.selected[0].chunk_id
