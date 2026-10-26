from uuid import uuid4

import pytest
from test_evidence_assembly import group_fixture


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "verdict,invalid,blocked",
    [
        ("CONFLICT", False, True),
        ("UNCERTAIN", False, True),
        ("NO_CONFLICT", False, False),
        ("NO_CONFLICT", True, True),
    ],
)
async def test_cross_document_conflict_contract(verdict, invalid, blocked):
    from efficiency_platform_agent.agents.customer_service.conflict_screen import (
        screen_conflicts,
    )

    _, parents = group_fixture()
    parents = (
        parents[0],
        parents[1].model_copy(
            update={"document_id": uuid4(), "document_version_id": uuid4()}
        ),
    )
    calls = []

    class Gateway:
        async def complete(self, stage, value, output_type):
            calls.append(stage)
            left, right = value["evidence"]
            return output_type.model_validate(
                {
                    "pairs": [
                        {
                            "left_parent_id": left["parent_id"],
                            "right_parent_id": right["parent_id"],
                            "same_scope": True,
                            "verdict": verdict,
                            "left_quote": "伪造" if invalid else left["content"],
                            "right_quote": right["content"],
                            "reason": "核对原文事实",
                        }
                    ]
                }
            )

    members = {
        (p.knowledge_base_id, p.document_id, p.document_version_id, p.index_release_id)
        for p in parents
    }
    result = await screen_conflicts(
        parents, question="问题", gateway=Gateway(), members=members, stage_bound=True
    )
    assert result.blocked is blocked
    assert calls == ["conflict_screen"] * (2 if invalid else 1)
    if invalid:
        assert result.errors == ("CONFLICT_QUOTE_INVALID",)


@pytest.mark.asyncio
async def test_markdown_escaped_quote_matches_same_source_text():
    from efficiency_platform_agent.agents.customer_service.conflict_screen import (
        screen_conflicts,
    )

    _, parents = group_fixture()
    parents = (
        parents[0].model_copy(update={"content": "群ID必须以oc\\_开头"}),
        parents[1].model_copy(
            update={"document_id": uuid4(), "content": "迭代周期固定为2周"}
        ),
    )

    class Gateway:
        async def complete(self, stage, value, output_type):
            return output_type.model_validate(
                {
                    "pairs": [
                        {
                            "left_parent_id": parents[0].parent_id,
                            "right_parent_id": parents[1].parent_id,
                            "same_scope": False,
                            "verdict": "NO_CONFLICT",
                            "left_quote": "oc_开头",
                            "right_quote": "2周",
                            "reason": "问题域不同",
                        }
                    ]
                }
            )

    members = {
        (p.knowledge_base_id, p.document_id, p.document_version_id, p.index_release_id)
        for p in parents
    }
    result = await screen_conflicts(
        parents, question="问题", gateway=Gateway(), members=members, stage_bound=True
    )
    assert result.errors == ()
    assert not result.blocked


@pytest.mark.asyncio
async def test_malformed_model_uuid_does_not_replace_trusted_pair_identity():
    from efficiency_platform_agent.agents.customer_service.conflict_screen import (
        screen_conflicts,
    )

    _, parents = group_fixture()
    parents = (
        parents[0],
        parents[1].model_copy(update={"document_id": uuid4()}),
    )

    class Gateway:
        async def complete(self, stage, value, output_type):
            return output_type.model_validate(
                {
                    "pairs": [
                        {
                            "left_parent_id": str(parents[0].parent_id),
                            "right_parent_id": "aee1ee5c-624d-5a19-b2b0a431639ce",
                            "same_scope": False,
                            "verdict": "NO_CONFLICT",
                            "left_quote": parents[0].content,
                            "right_quote": parents[1].content,
                            "reason": "问题域不同",
                        }
                    ]
                }
            )

    members = {
        (p.knowledge_base_id, p.document_id, p.document_version_id, p.index_release_id)
        for p in parents
    }
    result = await screen_conflicts(
        parents, question="问题", gateway=Gateway(), members=members, stage_bound=True
    )
    assert not result.blocked
    assert result.pairs[0].right_parent_id == parents[1].parent_id


@pytest.mark.asyncio
async def test_membership_missing_stage_and_empty_pair_fail_closed():
    from efficiency_platform_agent.agents.customer_service.conflict_screen import (
        screen_conflicts,
    )

    _, parents = group_fixture()
    parents = (parents[0], parents[1].model_copy(update={"document_id": uuid4()}))

    class Gateway:
        async def complete(self, stage, value, output_type):
            return output_type.model_validate({"pairs": []})

    members = {
        (p.knowledge_base_id, p.document_id, p.document_version_id, p.index_release_id)
        for p in parents
    }
    for bound, valid_members in [(False, members), (True, set()), (True, members)]:
        result = await screen_conflicts(
            parents,
            question="问题",
            gateway=Gateway(),
            members=valid_members,
            stage_bound=bound,
        )
        assert result.blocked
        assert result.errors


@pytest.mark.asyncio
async def test_conflict_runs_after_topk_before_budget_and_blocks_company_answer():
    from types import SimpleNamespace

    from test_answer_modes import Gateway, decision
    from test_equivalence import Scenario

    from efficiency_platform_agent.agents.customer_service.answer import generate_answer
    from efficiency_platform_agent.agents.customer_service.service import (
        CustomerServiceRunService,
    )
    from efficiency_platform_agent.agents.customer_service.state import (
        AnswerMode,
        IntentType,
    )
    from efficiency_platform_agent.agents.customer_service.sufficiency import (
        judge_sufficiency,
    )

    s = Scenario()
    s.items = (
        s.left,
        s.right.model_copy(
            update={"document_id": uuid4(), "document_version_id": uuid4()}
        ),
    )
    s.members = tuple(
        (x.knowledge_base_id, x.document_id, x.document_version_id, x.index_release_id)
        for x in s.items
    )
    s.bundle.rag_policy.context_token_limit = 1
    s.bundle.rag_policy.final_evidence_top_k = 2
    s.bundle.prompt_bindings += (
        SimpleNamespace(stage_key="conflict_screen", messages=()),
    )
    original = s.complete
    calls = []

    async def complete(stage, value, output_type):
        calls.append(stage)
        if stage == "conflict_screen":
            left, right = value["evidence"]
            return output_type.model_validate(
                {
                    "pairs": [
                        {
                            "left_parent_id": left["parent_id"],
                            "right_parent_id": right["parent_id"],
                            "same_scope": True,
                            "verdict": "CONFLICT",
                            "left_quote": left["content"],
                            "right_quote": right["content"],
                            "reason": "原文不一致",
                        }
                    ]
                }
            )
        return await original(stage, value, output_type)

    s.complete = complete
    trace = await s.search()
    assert trace.conflict_screen.blocked
    assert len(trace.assembly.selected_parents) == 2
    assert trace.assembly.excluded_parent_ids == ()
    suff = await judge_sufficiency(
        Gateway([]),
        "问题",
        trace.assembly.selected,
        conflict_screen=trace.conflict_screen,
    )
    answer = await generate_answer(
        Gateway([]),
        question="问题",
        intent=decision(IntentType.COMPANY_QUERY),
        evidence=trace.assembly.selected,
        sufficiency=suff,
    )
    assert answer.answer_mode == AnswerMode.INSUFFICIENT_EVIDENCE
    facts = CustomerServiceRunService._retrieval_facts(
        SimpleNamespace(retrieval_trace=trace, sufficiency=suff)
    )
    assert facts["conflict_screen"]["blocked"]
    assert facts["final_parent_candidates"] == [
        str(p.parent_id) for p in trace.assembly.candidate_parents
    ]
    s.bundle.rag_policy.final_evidence_top_k = 1
    calls.clear()
    trace = await s.search()
    assert "conflict_screen" not in calls


@pytest.mark.asyncio
async def test_repository_reads_frozen_table_identity_and_parent_order():
    from efficiency_platform_agent.agents.customer_service.vector_repository import (
        DocumentChunkRepository,
    )

    _, parents = group_fixture("TABLE", 0)
    p = parents[0]

    class Connection:
        async def execute(self, sql, params):
            assert "p.source_table_id" in sql
            assert "p.parent_no" in sql
            return [
                (
                    str(p.parent_id),
                    str(p.knowledge_base_id),
                    str(p.document_id),
                    str(p.document_version_id),
                    str(p.index_release_id),
                    p.document_title,
                    1,
                    None,
                    None,
                    None,
                    p.content,
                    p.content_hash,
                    20,
                    "TABLE",
                    "FULL_ONLY",
                    1,
                    0,
                )
            ]

    result = await DocumentChunkRepository(Connection()).get_parents(
        tenant_id="tenant",
        index_release_ids=(p.index_release_id,),
        parent_ids=(p.parent_id,),
    )
    assert result[0].source_table_id == 0
    assert result[0].parent_no == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    ["wrong_id", "missing_pair", "extra_pair", "false_scope_uncertain", "schema"],
)
async def test_untrusted_conflict_decisions_cannot_escape_gate(mutation):
    from efficiency_platform_agent.agents.customer_service.conflict_screen import (
        screen_conflicts,
    )

    _, parents = group_fixture()
    parents = (
        parents[0],
        parents[1].model_copy(
            update={"document_id": uuid4(), "document_version_id": uuid4()}
        ),
    )

    class Gateway:
        async def complete(self, stage, value, output_type):
            left, right = value["evidence"]
            pair = {
                "left_parent_id": left["parent_id"],
                "right_parent_id": right["parent_id"],
                "same_scope": True,
                "verdict": "NO_CONFLICT",
                "left_quote": left["content"],
                "right_quote": right["content"],
                "reason": "说明",
            }
            if mutation == "wrong_id":
                pair["left_parent_id"] = str(uuid4())
            if mutation == "false_scope_uncertain":
                pair.update(same_scope=False, verdict="UNCERTAIN")
            if mutation == "schema":
                pair["same_scope"] = "false"
            pairs = (
                []
                if mutation == "missing_pair"
                else [pair, pair]
                if mutation == "extra_pair"
                else [pair]
            )
            return output_type.model_validate({"pairs": pairs})

    members = {
        (p.knowledge_base_id, p.document_id, p.document_version_id, p.index_release_id)
        for p in parents
    }
    result = await screen_conflicts(
        parents, question="问题", gateway=Gateway(), members=members, stage_bound=True
    )
    if mutation == "wrong_id":
        assert not result.blocked
        assert result.pairs[0].left_parent_id == parents[0].parent_id
        assert result.pairs[0].right_parent_id == parents[1].parent_id
    else:
        assert result.blocked


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["left_quote", "right_quote", "reason"])
async def test_whitespace_cannot_prove_no_conflict(field):
    from efficiency_platform_agent.agents.customer_service.conflict_screen import (
        screen_conflicts,
    )

    _, parents = group_fixture()
    parents = (
        parents[0].model_copy(update={"content": "甲 规则"}),
        parents[1].model_copy(update={"document_id": uuid4(), "content": "乙 规则"}),
    )

    class Gateway:
        async def complete(self, stage, value, output_type):
            return output_type.model_validate(
                {
                    "pairs": [
                        {
                            "left_parent_id": parents[0].parent_id,
                            "right_parent_id": parents[1].parent_id,
                            "same_scope": False,
                            "verdict": "NO_CONFLICT",
                            "left_quote": parents[0].content,
                            "right_quote": parents[1].content,
                            "reason": "适用范围不同",
                            field: " ",
                        }
                    ]
                }
            )

    members = {
        (p.knowledge_base_id, p.document_id, p.document_version_id, p.index_release_id)
        for p in parents
    }
    result = await screen_conflicts(
        parents, question="问题", gateway=Gateway(), members=members, stage_bound=True
    )
    assert result.blocked
    assert result.errors == (
        "CONFLICT_REASON_INVALID" if field == "reason" else "CONFLICT_QUOTE_INVALID",
    )


@pytest.mark.asyncio
async def test_markdown_formatting_difference_keeps_verbatim_quote_valid():
    from efficiency_platform_agent.agents.customer_service.conflict_screen import (
        screen_conflicts,
    )

    _, parents = group_fixture()
    parents = (
        parents[0].model_copy(
            update={"content": "- **统一工具**：使用 Cursor 企业版。"}
        ),
        parents[1].model_copy(
            update={"document_id": uuid4(), "content": "群 ID 格式为 oc\\_xxxx。"}
        ),
    )

    class Gateway:
        async def complete(self, stage, value, output_type):
            return output_type.model_validate(
                {
                    "pairs": [
                        {
                            "left_parent_id": parents[0].parent_id,
                            "right_parent_id": parents[1].parent_id,
                            "same_scope": False,
                            "verdict": "NO_CONFLICT",
                            "left_quote": "统一工具：使用 Cursor 企业版。",
                            "right_quote": "群 ID 格式为 oc_xxxx。",
                            "reason": "业务对象不同",
                        }
                    ]
                }
            )

    members = {
        (p.knowledge_base_id, p.document_id, p.document_version_id, p.index_release_id)
        for p in parents
    }
    result = await screen_conflicts(
        parents, question="问题", gateway=Gateway(), members=members, stage_bound=True
    )

    assert result.errors == ()
    assert result.blocked is False
