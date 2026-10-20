"""正式模型决策适配器只接纳有界、可回查的候选。"""

import json
from importlib import import_module, util
from types import SimpleNamespace

import pytest

from efficiency_platform_agent.context.builder import ContextBuilder
from efficiency_platform_agent.contracts.intent_v2 import BudgetLeaseReferenceV2
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.run import RunContext
from efficiency_platform_agent.harness.research_local_runtime import (
    build_local_research_binding,
)
from tests.unit.capabilities.research_v2._delivery_support import delivery_facts
from tests.unit.harness.test_research_local_tools import NOW


def module():
    name = "efficiency_platform_agent.capabilities.research.v2.model_decisions"
    assert util.find_spec(name) is not None, "RESEARCH_MODEL_DECISIONS_MISSING"
    return import_module(name)


class Model:
    def __init__(self, output):
        self.output, self.calls = output, []

    async def complete(self, demand, request, **kwargs):
        self.calls.append((demand, request, kwargs))
        output = self.output(demand, request) if callable(self.output) else self.output
        return SimpleNamespace(
            result=SimpleNamespace(
                error=None, message=SimpleNamespace(content=json.dumps(output))
            ),
            attempts=(object(),),
        )


def setup(output, *, prompt_assembler=None):
    brief, _, document, *_ = delivery_facts()
    remaining = RemainingBudget(50, 60, 100_000, 20_000, 100_000, 180_000)
    binding = build_local_research_binding(
        tenant_id="t",
        run_id="r",
        lease_id="lease",
        remaining=remaining,
        now=NOW,
        clock_ms=lambda: int(NOW.timestamp() * 1000),
    )
    model = Model(output)
    decisions = module().ResearchModelDecisions(
        model_runtime=model,
        context_builder=ContextBuilder(),
        run_context=RunContext("r", "t", "u", "trace"),
        binding=binding,
        brief=brief,
        remaining_budget=remaining,
        prompt_assembler=prompt_assembler,
    )
    return decisions, model, binding, brief, document


class DatabasePromptAssembler:
    def __init__(self):
        self.calls = []

    async def assemble(self, **request):
        self.calls.append(request)
        return SimpleNamespace(
            prompt_key=request["prompt_key"],
            semantic_version="2.0.0",
            messages=(
                SimpleNamespace(role="system", content="research system"),
                SimpleNamespace(role="developer", content="research contract"),
                SimpleNamespace(role="user", content="research payload"),
            ),
            rendered_chars=48,
        )


def relevance_output():
    brief, _, document, *_ = delivery_facts()
    return {
        "document_id": document.document_id,
        "document_content_hash": document.content_hash,
        "brief_digest": brief.canonical_digest(),
        "outcome": "irrelevant",
        "requirement_ids": [],
        "source_excerpt": document.text,
        "prompt_version": "research.v2.relevance@1.1.0",
    }


@pytest.mark.asyncio
async def test_relevance_uses_context_builder_model_runtime_and_same_lease():
    decisions, model, binding, brief, document = setup(relevance_output())
    result = await decisions.relevance(
        brief, (document,), BudgetLeaseReferenceV2(lease_id="lease", version=0)
    )
    assert result[0].outcome == "irrelevant"
    _, request, kwargs = model.calls[0]
    assert document.text in request.messages[-1].content
    assert request.messages[-1].role == "user"
    assert json.loads(request.messages[-1].content)["brief_digest"] == brief.canonical_digest()
    response_format = dict(request.options.items)["response_format"]
    assert dict(response_format.items) == {"type": "json_object"}
    assert kwargs["lease_context"].port is binding.port
    assert kwargs["lease_context"].scope == binding.scope


@pytest.mark.asyncio
async def test_relevance_accepts_exact_excerpt_from_document_title():
    output = relevance_output()
    brief, _, document, *_ = delivery_facts()
    output["source_excerpt"] = document.title
    decisions, *_ = setup(output)

    result = await decisions.relevance(
        brief, (document,), BudgetLeaseReferenceV2(lease_id="lease", version=0)
    )

    assert result[0].source_excerpt == document.title


@pytest.mark.asyncio
async def test_relevance_batches_a_diverse_bounded_candidate_set():
    brief, _, template, *_ = delivery_facts()
    documents = tuple(
        template.model_copy(
            update={
                "document_id": f"doc-{index:02d}",
                "candidate_id": f"candidate-{index:02d}",
                "source_id": f"source-{index % 3}",
                "source_item_id": f"item-{index:02d}",
                "original_url": f"https://source-{index % 3}.example/{index}",
                "canonical_url": f"https://source-{index % 3}.example/{index}",
                "content_hash": f"{index:064x}",
                "artifact_ref": f"artifact-{index:02d}",
            }
        )
        for index in range(15)
    )

    def batched_output(_demand, request):
        payload = json.loads(request.messages[-1].content)
        source_documents = payload.get("documents") or [payload["document"]]
        decisions = [
            {
                "document_id": item["document_id"],
                "document_content_hash": item["content_hash"],
                "brief_digest": payload["brief_digest"],
                "outcome": "irrelevant",
                "requirement_ids": [],
                "source_excerpt": item["title"],
                "prompt_version": payload["prompt_version"],
            }
            for item in source_documents
        ]
        return {"decisions": decisions}

    decisions, model, *_ = setup(batched_output)
    result = await decisions.relevance(
        brief, documents, BudgetLeaseReferenceV2(lease_id="lease", version=0)
    )

    assert len(model.calls) == 1
    assert len(result) == 10
    selected = {item.document_id for item in result}
    assert {item.source_id for item in documents if item.document_id in selected} == {
        "source-0",
        "source-1",
        "source-2",
    }


def test_relevance_candidate_limit_keeps_each_available_source_represented():
    brief, _, template, *_ = delivery_facts()
    hot = tuple(
        template.model_copy(
            update={
                "document_id": f"hot-{index}",
                "candidate_id": f"hot-candidate-{index}",
                "source_id": "hot-source",
                "source_item_id": f"hot-item-{index}",
                "title": "Acme AI agent release",
                "text": "Acme announced an AI agent release with model updates.",
                "content_hash": f"{index + 100:064x}",
                "artifact_ref": f"hot-artifact-{index}",
            }
        )
        for index in range(12)
    )
    cold = template.model_copy(
        update={
            "document_id": "cold-1",
            "candidate_id": "cold-candidate-1",
            "source_id": "cold-source",
            "source_item_id": "cold-item-1",
            "title": "Unrelated weather update",
            "text": "A weather update without the requested entity.",
            "content_hash": "f" * 64,
            "artifact_ref": "cold-artifact-1",
        }
    )

    selected = module()._select_relevance_candidates(brief, (*hot, cold))

    assert len(selected) == 10
    assert {item.source_id for item in selected} == {"hot-source", "cold-source"}


def test_relevance_candidate_limit_expands_for_top_ten_request():
    brief, _, template, *_ = delivery_facts()
    brief = brief.model_copy(
        update={
            "count_policy": brief.count_policy.model_copy(
                update={"target": 10, "minimum": 10}
            )
        }
    )
    documents = tuple(
        template.model_copy(
            update={
                "document_id": f"doc-{index:02d}",
                "candidate_id": f"candidate-{index:02d}",
                "source_item_id": f"item-{index:02d}",
                "content_hash": f"{index:064x}",
                "artifact_ref": f"artifact-{index:02d}",
            }
        )
        for index in range(25)
    )

    selected = module()._select_relevance_candidates(brief, documents)

    assert len(selected) == 15


@pytest.mark.asyncio
async def test_relevance_batch_drops_non_verbatim_excerpt_instead_of_repairing_it():
    brief, _, template, *_ = delivery_facts()
    documents = (
        template,
        template.model_copy(
            update={
                "document_id": "doc-2",
                "candidate_id": "candidate-2",
                "source_item_id": "item-2",
                "canonical_url": "https://example.test/doc-2",
                "original_url": "https://example.test/doc-2",
                "content_hash": "2" * 64,
                "artifact_ref": "artifact-2",
            }
        ),
    )

    def output(_demand, request):
        payload = json.loads(request.messages[-1].content)
        return {
            "decisions": [
                {
                    "document_id": item["document_id"],
                    "document_content_hash": item["content_hash"],
                    "brief_digest": payload["brief_digest"],
                    "outcome": "relevant",
                    "requirement_ids": [],
                    "source_excerpt": (
                        item["title"] if index == 0 else "模型改写、无法逐字回查的内容"
                    ),
                    "prompt_version": payload["prompt_version"],
                }
                for index, item in enumerate(payload["documents"])
            ]
        }

    decisions, *_ = setup(output)
    result = await decisions.relevance(
        brief, documents, BudgetLeaseReferenceV2(lease_id="lease", version=0)
    )

    assert len(result) == 1
    assert result[0].source_excerpt in {
        document.title for document in documents
    }
    assert result[0].source_excerpt != "模型改写、无法逐字回查的内容"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("document_id", "invented-document"),
        ("url", "https://invented.example/x"),
        ("char_start", 99999),
        ("source_excerpt", "invented quote"),
        ("brief_digest", "f" * 64),
    ],
)
async def test_relevance_rejects_invented_identity_url_or_offsets(field, value):
    output = relevance_output()
    output[field] = value
    decisions, _, _, brief, document = setup(output)
    with pytest.raises(ValueError, match="RESEARCH_MODEL_DECISION_INVALID"):
        await decisions.relevance(
            brief, (document,), BudgetLeaseReferenceV2(lease_id="lease", version=0)
        )


@pytest.mark.asyncio
async def test_wrong_lease_is_rejected_before_model():
    decisions, model, _, brief, document = setup(relevance_output())
    with pytest.raises(ValueError, match="RESEARCH_MODEL_SCOPE_MISMATCH"):
        await decisions.relevance(
            brief, (document,), BudgetLeaseReferenceV2(lease_id="foreign", version=0)
        )
    assert model.calls == []


@pytest.mark.asyncio
async def test_exhausted_shared_budget_blocks_model_before_dispatch():
    from efficiency_platform_agent.core.budget_lease import BudgetCharge

    decisions, model, binding, brief, document = setup(relevance_output())
    reservation = await binding.port.reserve(
        binding.scope, "consume", BudgetCharge(input_tokens=100_000), 0
    )
    await binding.port.mark_dispatched(reservation.reservation_id)
    snapshot = await binding.port.settle(
        reservation.reservation_id, BudgetCharge(input_tokens=100_000), "success"
    )
    binding.update_version(snapshot.version)
    with pytest.raises(ValueError, match="RESEARCH_MODEL_CONTEXT_TOO_LARGE"):
        await decisions.relevance(
            brief,
            (document,),
            BudgetLeaseReferenceV2(lease_id="lease", version=binding.version),
        )
    assert model.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        {"url": "https://invented.example"},
        {"char_start": 9999},
        {"support_refs": ["invented-ref"]},
        {"text": "Acme announced https://invented.example/news"},
    ],
)
async def test_claim_adapter_rejects_invented_urls_offsets_and_evidence(extra):
    from efficiency_platform_agent.capabilities.research.v2.evidence import (
        EvidenceContextV2,
    )
    from efficiency_platform_agent.capabilities.research.v2.source_families import (
        SourceFamilyResolver,
    )

    brief, _, document, event, _, ref = delivery_facts()
    proposal = {
        "proposal_id": "p",
        "claim_key": "announcement",
        "brief_digest": brief.canonical_digest(),
        "prompt_version": "research.v2.claims@1.0.0",
        "event_id": event.event_id,
        "text": document.text,
        "claim_type": "announcement",
        "subject": "Acme",
        "assertion_mode": "attributed",
        "attributed_to": "Acme",
        "support_refs": [ref.evidence_id],
    }
    proposal.update(extra)
    decisions, *_ = setup([proposal])
    context = EvidenceContextV2(
        brief_digest=brief.canonical_digest(),
        documents=(document,),
        evidence_refs=(ref,),
        source_families=SourceFamilyResolver().resolve((document,)),
    )
    with pytest.raises(ValueError, match="RESEARCH_MODEL_DECISION_INVALID"):
        await (
            module()
            .ResearchClaimModelAdapter(decisions)
            .propose(
                (event,), context, BudgetLeaseReferenceV2(lease_id="lease", version=0)
            )
        )


@pytest.mark.asyncio
async def test_claim_adapter_accepts_json_object_proposals_wrapper():
    from efficiency_platform_agent.capabilities.research.v2.evidence import (
        EvidenceContextV2,
    )
    from efficiency_platform_agent.capabilities.research.v2.source_families import (
        SourceFamilyResolver,
    )

    brief, _, document, event, _, ref = delivery_facts()
    proposal = {
        "proposal_id": "p",
        "claim_key": "announcement",
        "brief_digest": brief.canonical_digest(),
        "prompt_version": "research.v2.claims@1.0.0",
        "event_id": event.event_id,
        "text": document.text,
        "claim_type": "announcement",
        "subject": "Acme",
        "assertion_mode": "attributed",
        "attributed_to": "Acme",
        "support_refs": [ref.evidence_id],
    }
    decisions, *_ = setup({"proposals": [proposal]})
    context = EvidenceContextV2(
        brief_digest=brief.canonical_digest(),
        documents=(document,),
        evidence_refs=(ref,),
        source_families=SourceFamilyResolver().resolve((document,)),
    )

    result = await module().ResearchClaimModelAdapter(decisions).propose(
        (event,), context, BudgetLeaseReferenceV2(lease_id="lease", version=0)
    )

    assert result[0].proposal_id == "p"


@pytest.mark.asyncio
async def test_claim_adapter_repairs_policy_invalid_first_response():
    from efficiency_platform_agent.capabilities.research.v2.evidence import (
        EvidenceContextV2,
    )
    from efficiency_platform_agent.capabilities.research.v2.source_families import (
        SourceFamilyResolver,
    )

    brief, _, document, event, _, ref = delivery_facts()
    proposal = {
        "proposal_id": "p",
        "claim_key": "announcement",
        "brief_digest": brief.canonical_digest(),
        "prompt_version": "research.v2.claims@1.0.0",
        "event_id": event.event_id,
        "text": document.text,
        "claim_type": "announcement",
        "subject": "Acme",
        "assertion_mode": "attributed",
        "attributed_to": "Acme",
        "support_refs": [ref.evidence_id],
    }
    call_count = 0

    def output(_demand, request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [{**proposal, "text": "https://invented.example/news"}]
        assert "上次输出包含未授权事件、URL 或证据引用" in request.messages[-1].content
        return [proposal]

    decisions, model, *_ = setup(output)
    context = EvidenceContextV2(
        brief_digest=brief.canonical_digest(),
        documents=(document,),
        evidence_refs=(ref,),
        source_families=SourceFamilyResolver().resolve((document,)),
    )

    result = await module().ResearchClaimModelAdapter(decisions).propose(
        (event,), context, BudgetLeaseReferenceV2(lease_id="lease", version=0)
    )

    assert len(model.calls) == 2
    assert result[0].proposal_id == "p"


@pytest.mark.asyncio
async def test_claim_adapter_keeps_safe_items_from_mixed_policy_batch():
    from efficiency_platform_agent.capabilities.research.v2.evidence import (
        EvidenceContextV2,
    )
    from efficiency_platform_agent.capabilities.research.v2.source_families import (
        SourceFamilyResolver,
    )

    brief, _, document, event, _, ref = delivery_facts()
    proposal = {
        "proposal_id": "safe",
        "claim_key": "announcement",
        "brief_digest": brief.canonical_digest(),
        "prompt_version": "research.v2.claims@1.0.0",
        "event_id": event.event_id,
        "text": document.text,
        "claim_type": "announcement",
        "subject": "Acme",
        "assertion_mode": "attributed",
        "attributed_to": "Acme",
        "support_refs": [ref.evidence_id],
    }
    decisions, model, *_ = setup(
        {"proposals": [proposal, {**proposal, "proposal_id": "bad", "text": "https://invalid.example"}]}
    )
    context = EvidenceContextV2(
        brief_digest=brief.canonical_digest(),
        documents=(document,),
        evidence_refs=(ref,),
        source_families=SourceFamilyResolver().resolve((document,)),
    )

    result = await module().ResearchClaimModelAdapter(
        decisions, minimum_valid_event_count=1
    ).propose(
        (event,), context, BudgetLeaseReferenceV2(lease_id="lease", version=0)
    )

    assert len(model.calls) == 1
    assert [item.proposal_id for item in result] == ["safe"]


@pytest.mark.asyncio
async def test_claim_adapter_retries_invalid_model_claim_without_evidence_closure():
    from efficiency_platform_agent.capabilities.research.v2.evidence import (
        EvidenceContextV2,
        build_evidence_ref,
    )
    from efficiency_platform_agent.capabilities.research.v2.source_families import (
        SourceFamilyResolver,
    )

    brief, _, document, event, _, ref = delivery_facts()
    second_document = document.model_copy(
        update={
            "document_id": "doc-2",
            "candidate_id": "candidate-2",
            "source_id": "source-2",
            "source_item_id": "item-2",
            "canonical_url": "https://second.example/result",
            "original_url": "https://second.example/result",
            "publisher_id": "second.example",
            "title": "Beta 发布公告",
            "text": "Beta announced a new AI model.",
            "content_hash": "b" * 64,
            "artifact_ref": "artifact:2",
        }
    )
    second_ref = build_evidence_ref(second_document, 0, len(second_document.text))
    second_event = event.model_copy(
        update={
            "event_id": "event-2",
            "entity_names": ("Beta",),
            "member_document_ids": (second_document.document_id,),
            "representative_document_id": second_document.document_id,
        }
    )
    proposal = {
        "proposal_id": "model-proposal",
        "claim_key": "announcement",
        "brief_digest": brief.canonical_digest(),
        "prompt_version": "research.v2.claims@1.0.0",
        "event_id": event.event_id,
        "text": document.text,
        "claim_type": "announcement",
        "subject": "Acme",
        "assertion_mode": "attributed",
        "attributed_to": "Acme",
        "support_refs": [ref.evidence_id],
    }
    invalid_second_proposal = {
        **proposal,
        "proposal_id": "model-proposal-invalid",
        "event_id": second_event.event_id,
        "text": "Beta announced a 99% result.",
        "subject": "Beta",
        "value_text": "99%",
        "numeric_value": 99,
        "unit": "percent",
        "claim_time": second_document.published_at.isoformat(),
        "support_refs": [second_ref.evidence_id],
    }
    call_count = 0

    def output(_demand, _request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"proposals": [proposal, invalid_second_proposal]}
        return {
            "proposals": [
                {
                    **proposal,
                    "proposal_id": "model-proposal-retry",
                    "event_id": second_event.event_id,
                    "text": second_document.text,
                    "subject": "Beta",
                    "attributed_to": "Beta",
                    "claim_time": second_document.published_at.isoformat(),
                    "support_refs": [second_ref.evidence_id],
                }
            ]
        }

    decisions, model, *_ = setup(output)
    context = EvidenceContextV2(
        brief_digest=brief.canonical_digest(),
        documents=(document, second_document),
        evidence_refs=(ref, second_ref),
        source_families=SourceFamilyResolver().resolve(
            (document, second_document)
        ),
    )

    result = await module().ResearchClaimModelAdapter(decisions).propose(
        (event, second_event),
        context,
        BudgetLeaseReferenceV2(lease_id="lease", version=0),
    )

    assert len(model.calls) == 2
    assert [item.proposal_id for item in result] == [
        "model-proposal",
        "model-proposal-retry",
    ]

    call_count = 0
    calls_before = len(model.calls)
    bounded = await module().ResearchClaimModelAdapter(
        decisions, minimum_valid_event_count=1
    ).propose(
        (event, second_event),
        context,
        BudgetLeaseReferenceV2(lease_id="lease", version=0),
    )

    assert len(model.calls) == calls_before + 1
    assert [item.proposal_id for item in bounded] == ["model-proposal"]


@pytest.mark.asyncio
async def test_real_model_runtime_charges_the_original_parent_lease():
    from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
    from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
    from efficiency_platform_agent.providers.llm.registry import ModelProviderRegistry
    from efficiency_platform_agent.routing.model_router import ModelPolicyRouter
    from tests.unit.capabilities.test_model_runtime import result

    decisions, _, binding, brief, document = setup(relevance_output())
    registry = ModelProviderRegistry()
    registry.register(
        "fake_balanced",
        FakeModelProvider("fake_balanced", [result(json.dumps(relevance_output()))]),
    )
    decisions.model_runtime = ModelRuntime(ModelPolicyRouter(), registry)
    await decisions.relevance(
        brief, (document,), BudgetLeaseReferenceV2(lease_id="lease", version=0)
    )
    snapshot = await binding.port.snapshot(binding.scope)
    assert snapshot.used.calls == 1
    assert snapshot.used.input_tokens == 2
    assert snapshot.used.cost_microunits == 5
    assert decisions.model_calls == 1


@pytest.mark.asyncio
async def test_cluster_adapter_rejects_unknown_document():
    from efficiency_platform_agent.capabilities.research.v2.clustering import (
        ClusterBucketV2,
    )

    brief, _, document, *_ = delivery_facts()
    decisions, *_ = setup(
        [
            {
                "proposal_id": "p",
                "brief_digest": brief.canonical_digest(),
                "prompt_version": "research.v2.cluster@1.0.0",
                "members": [
                    {
                        "document_id": "invented",
                        "event_type": "announcement",
                        "semantic_equivalence": "same_event",
                    }
                ],
                "merge_basis": ["same announcement"],
            }
        ]
    )
    with pytest.raises(ValueError, match="RESEARCH_MODEL_DECISION_INVALID"):
        await (
            module()
            .ResearchClusterModelAdapter(decisions)
            .propose(
                ClusterBucketV2(bucket_id="b", documents=(document,)),
                brief,
                BudgetLeaseReferenceV2(lease_id="lease", version=0),
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    ["event_type", "product_version", "entity_names", "merge_basis", "proposal_id"],
)
@pytest.mark.parametrize(
    "value",
    [
        "announcement https://invented.example/news",
        "ftp://invented.example/item",
        "//invented.example/item",
    ],
)
async def test_cluster_adapter_rejects_urls_in_every_string_field(field, value):
    from efficiency_platform_agent.capabilities.research.v2.clustering import (
        ClusterBucketV2,
    )

    brief, _, document, *_ = delivery_facts()
    proposal = {
        "proposal_id": "p",
        "brief_digest": brief.canonical_digest(),
        "prompt_version": "research.v2.cluster@1.0.0",
        "members": [
            {
                "document_id": document.document_id,
                "event_type": "announcement",
                "semantic_equivalence": "same_event",
            }
        ],
        "entity_names": ["Acme"],
        "merge_basis": ["same announcement"],
    }
    if field in {"event_type", "product_version"}:
        proposal["members"][0][field] = value
    else:
        proposal[field] = [value] if field in {"entity_names", "merge_basis"} else value
    decisions, *_ = setup([proposal])
    with pytest.raises(ValueError, match="RESEARCH_MODEL_DECISION_INVALID"):
        await (
            module()
            .ResearchClusterModelAdapter(decisions)
            .propose(
                ClusterBucketV2(bucket_id="b", documents=(document,)),
                brief,
                BudgetLeaseReferenceV2(lease_id="lease", version=0),
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    ["event_type", "product_version", "entity_names", "merge_basis", "proposal_id"],
)
@pytest.mark.parametrize(
    "value,rejected",
    [
        ("announcement https://invented.example/news", True),
        ("//[2001:db8::1]/news", True),
        ("//例子.测试/news", True),
        ("  //例子.测试/news", True),
        ("SOURCE_URL", True),
        ("Python x//2 uses floor division", False),
    ],
)
async def test_real_cluster_pipeline_distinguishes_url_authority_from_natural_text(
    field, value, rejected
):
    from efficiency_platform_agent.capabilities.research.v2.clustering import (
        EventClusterer,
    )

    brief, _, document, *_ = delivery_facts()
    original_url = document.canonical_url
    value = original_url if value == "SOURCE_URL" else value
    proposal = {
        "proposal_id": "p",
        "brief_digest": brief.canonical_digest(),
        "prompt_version": "research.v2.cluster@1.0.0",
        "members": [
            {
                "document_id": document.document_id,
                "event_type": "announcement",
                "semantic_equivalence": "same_event",
            }
        ],
        "entity_names": ["Acme"],
        "merge_basis": ["same announcement"],
    }
    if field in {"event_type", "product_version"}:
        proposal["members"][0][field] = value
    else:
        proposal[field] = [value] if field in {"entity_names", "merge_basis"} else value
    decisions, *_ = setup([proposal])
    clusterer = EventClusterer(module().ResearchClusterModelAdapter(decisions))
    lease = BudgetLeaseReferenceV2(lease_id="lease", version=0)
    if rejected:
        with pytest.raises(ValueError, match="RESEARCH_MODEL_DECISION_INVALID"):
            await clusterer.cluster((document,), brief, lease)
    else:
        result = await clusterer.cluster((document,), brief, lease)
        assert result.rejected_proposal_count == 0
        assert len(result.events) == 1
        assert result.events[0].cluster_confidence == "confirmed"
        assert result.events[0].member_document_ids == (document.document_id,)
    assert document.canonical_url == original_url


@pytest.mark.asyncio
async def test_plan_adapter_cannot_invent_source_action_or_url():
    from efficiency_platform_agent.contracts.research_v2 import (
        BudgetSnapshotV2,
        CollectionHistoryV2,
        QualityReportV2,
    )

    decisions, _, _, brief, _ = setup({"action_ids": ["https://invented.example/"]})
    with pytest.raises(ValueError, match="RESEARCH_MODEL_DECISION_INVALID"):
        await (
            module()
            .ResearchPlanModelAdapter(decisions, ())
            .propose(
                brief,
                QualityReportV2(
                    report_id="q",
                    brief_digest=brief.canonical_digest(),
                    policy_version="v2",
                    hard_gates_passed=False,
                    coverage_ratio=0,
                ),
                CollectionHistoryV2(rounds=0, no_gain_rounds=0),
                BudgetSnapshotV2(
                    lease_id="lease", version=0, remaining_calls=5, remaining_bytes=100
                ),
            )
        )


@pytest.mark.asyncio
async def test_plan_adapter_materializes_model_query_with_server_owned_scope():
    from efficiency_platform_agent.contracts.research_v2 import (
        BudgetSnapshotV2,
        CollectionActionV2,
        CollectionHistoryV2,
        QualityGapV2,
        QualityReportV2,
    )
    from efficiency_platform_agent.orchestration.research_v2.planner import (
        action_fingerprint,
    )

    decisions, _, _, brief, _ = setup(
        {
            "proposals": [
                {
                    "gap_id": "gap-count",
                    "source_id": "source-1",
                    "action_kind": "search_alternative",
                    "query": "AI model release funding open source",
                    "cursor": None,
                }
            ],
            "stop_reason": None,
        }
    )
    gap = QualityGapV2(
        gap_id="gap-count",
        requirement_id="count_policy",
        code="COUNT_EXACT_UNMET",
        detail="need more events",
        recoverable=True,
    )
    template = CollectionActionV2(
        action_id=action_fingerprint(
            brief.intent_revision, gap, "source-1", brief.topic, None
        ),
        gap_id=gap.gap_id,
        gap_code=gap.code,
        action_kind="search_alternative",
        source_id="source-1",
        requirement_ids=(gap.requirement_id,),
        query=brief.topic,
        time_window=brief.time_window,
        revision=brief.intent_revision,
    )

    plan = await module().ResearchPlanModelAdapter(decisions, (template,)).propose(
        brief,
        QualityReportV2(
            report_id="q",
            brief_digest=brief.canonical_digest(),
            policy_version="v2",
            hard_gates_passed=False,
            gaps=(gap,),
            coverage_ratio=0,
        ),
        CollectionHistoryV2(rounds=0, no_gain_rounds=0),
        BudgetSnapshotV2(
            lease_id="lease", version=0, remaining_calls=5, remaining_bytes=100
        ),
    )

    assert len(plan.actions) == 1
    action = plan.actions[0]
    assert action.query == "AI model release funding open source"
    assert action.time_window == brief.time_window
    assert action.revision == brief.intent_revision
    assert action.action_id == action_fingerprint(
        brief.intent_revision, gap, "source-1", action.query, None
    )


def test_collection_history_carries_progress_and_failure_memory():
    from efficiency_platform_agent.contracts.research_v2 import CollectionHistoryV2

    history = CollectionHistoryV2(
        rounds=2,
        no_gain_rounds=1,
        attempted_queries=("AI launch", "AI funding"),
        failed_queries=("AI funding",),
        failed_source_ids=("source-2",),
        qualified_event_count=3,
        remaining_target_count=7,
    )

    assert history.attempted_queries == ("AI launch", "AI funding")
    assert history.failed_queries == ("AI funding",)
    assert history.failed_source_ids == ("source-2",)
    assert history.qualified_event_count == 3
    assert history.remaining_target_count == 7


@pytest.mark.asyncio
async def test_replan_uses_database_multi_role_prompt_when_assembler_is_bound():
    from efficiency_platform_agent.contracts.research_v2 import (
        BudgetSnapshotV2,
        CollectionActionV2,
        CollectionHistoryV2,
        QualityGapV2,
        QualityReportV2,
    )
    from efficiency_platform_agent.orchestration.research_v2.planner import (
        action_fingerprint,
    )

    assembler = DatabasePromptAssembler()
    decisions, model, _, brief, _ = setup(
        {"action_ids": [], "stop_reason": "PLAN_EXHAUSTED"},
        prompt_assembler=assembler,
    )
    gap = QualityGapV2(
        gap_id="gap-count",
        requirement_id="count_policy",
        code="COUNT_EXACT_UNMET",
        detail="need more events",
        recoverable=True,
    )
    template = CollectionActionV2(
        action_id=action_fingerprint(
            brief.intent_revision, gap, "source-1", brief.topic, None
        ),
        gap_id=gap.gap_id,
        gap_code=gap.code,
        action_kind="search_alternative",
        source_id="source-1",
        requirement_ids=(gap.requirement_id,),
        query=brief.topic,
        time_window=brief.time_window,
        revision=brief.intent_revision,
    )

    await module().ResearchPlanModelAdapter(decisions, (template,)).propose(
        brief,
        QualityReportV2(
            report_id="q",
            brief_digest=brief.canonical_digest(),
            policy_version="v2",
            hard_gates_passed=False,
            gaps=(gap,),
            coverage_ratio=0,
        ),
        CollectionHistoryV2(rounds=0, no_gain_rounds=0),
        BudgetSnapshotV2(
            lease_id="lease", version=0, remaining_calls=5, remaining_bytes=100
        ),
    )

    assert assembler.calls[0]["prompt_key"] == "research.plan"
    _, request, _ = model.calls[0]
    assert [message.role for message in request.messages] == [
        "system",
        "developer",
        "user",
    ]
