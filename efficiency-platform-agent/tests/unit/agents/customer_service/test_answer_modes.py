from __future__ import annotations

from hashlib import sha256
from uuid import UUID

import pytest
from pydantic import BaseModel

from efficiency_platform_agent.agents.customer_service.answer import generate_answer
from efficiency_platform_agent.agents.customer_service.state import (
    AnswerMode,
    CompanyParagraph,
    CompanySection,
    CustomerServiceAnswer,
    Evidence,
    GeneralAdvice,
    IntentDecision,
    IntentType,
    SufficiencyDecision,
)
from efficiency_platform_agent.agents.customer_service.sufficiency import (
    judge_sufficiency,
)

CHUNK_ID = UUID("90000000-0000-0000-0000-000000000001")


class Gateway:
    def __init__(self, values: list[BaseModel]) -> None:
        self.values = values
        self.stages: list[str] = []

    async def complete(
        self, stage_key: str, input_value: object, output_type: type[BaseModel]
    ):
        self.stages.append(stage_key)
        value = self.values.pop(0)
        assert isinstance(value, output_type)
        return value


def evidence() -> tuple[Evidence, ...]:
    content = "员工年假按已发布制度执行。"
    return (
        Evidence(
            chunk_id=CHUNK_ID,
            knowledge_base_id=UUID("90000000-0000-0000-0000-000000000002"),
            document_id=UUID("90000000-0000-0000-0000-000000000003"),
            document_version_id=UUID("90000000-0000-0000-0000-000000000004"),
            index_release_id=UUID("90000000-0000-0000-0000-000000000005"),
            document_title="员工制度",
            version_no=1,
            section_path="年假",
            page_no=1,
            content=content,
            content_hash=sha256(content.encode()).hexdigest(),
            score=0.9,
        ),
    )


def decision(kind: IntentType) -> IntentDecision:
    return IntentDecision(
        intent_type=kind,
        requires_company_knowledge=kind
        in {IntentType.COMPANY_QUERY, IntentType.MIXED_QUERY},
        requires_general_advice=kind
        in {IntentType.GENERAL_QUERY, IntentType.MIXED_QUERY},
        missing_field="所属地区" if kind is IntentType.AMBIGUOUS_QUERY else None,
        normalized_question="年假怎么申请？",
    )


def sufficient() -> SufficiencyDecision:
    return SufficiencyDecision(
        sufficient=True,
        supported_claims=(
            {"claim": "年假按制度执行", "supporting_chunk_ids": [CHUNK_ID]},
        ),
        unsupported_claims=(),
        conflicts=(),
        recommended_mode=AnswerMode.COMPANY_KNOWLEDGE,
    )


@pytest.mark.parametrize(
    ("intent_type", "answer", "mode"),
    [
        (
            IntentType.COMPANY_QUERY,
            CustomerServiceAnswer(
                contract_version="customer-service-answer/1",
                answer_mode=AnswerMode.COMPANY_KNOWLEDGE,
                company_sections=(
                    CompanySection(
                        title="公司制度",
                        paragraphs=(
                            CompanyParagraph(
                                text="年假按制度执行。",
                                supporting_chunk_ids=(CHUNK_ID,),
                            ),
                        ),
                    ),
                ),
            ),
            AnswerMode.COMPANY_KNOWLEDGE,
        ),
        (
            IntentType.MIXED_QUERY,
            CustomerServiceAnswer(
                contract_version="customer-service-answer/1",
                answer_mode=AnswerMode.MIXED,
                company_sections=(
                    CompanySection(
                        title="公司制度",
                        paragraphs=(
                            CompanyParagraph(
                                text="年假按制度执行。",
                                supporting_chunk_ids=(CHUNK_ID,),
                            ),
                        ),
                    ),
                ),
                general_advice=GeneralAdvice(paragraphs=("提前安排工作交接。",)),
            ),
            AnswerMode.MIXED,
        ),
        (
            IntentType.GENERAL_QUERY,
            CustomerServiceAnswer(
                contract_version="customer-service-answer/1",
                answer_mode=AnswerMode.GENERAL_ADVICE,
                general_advice=GeneralAdvice(paragraphs=("保持规律作息。",)),
            ),
            AnswerMode.GENERAL_ADVICE,
        ),
    ],
)
async def test_model_driven_answer_modes(intent_type, answer, mode) -> None:
    gateway = Gateway([answer])
    result = await generate_answer(
        gateway,
        question="问题",
        intent=decision(intent_type),
        evidence=evidence() if intent_type is not IntentType.GENERAL_QUERY else (),
        sufficiency=sufficient()
        if intent_type is not IntentType.GENERAL_QUERY
        else None,
    )
    assert result.answer_mode is mode


async def test_ambiguous_and_insufficient_do_not_invent_company_facts() -> None:
    clarify = await generate_answer(
        Gateway([]),
        question="问题",
        intent=decision(IntentType.AMBIGUOUS_QUERY),
        evidence=(),
        sufficiency=None,
    )
    insufficient = await generate_answer(
        Gateway([]),
        question="问题",
        intent=decision(IntentType.COMPANY_QUERY),
        evidence=(),
        sufficiency=SufficiencyDecision(
            sufficient=False,
            supported_claims=(),
            unsupported_claims=("缺少制度",),
            conflicts=(),
            recommended_mode=AnswerMode.INSUFFICIENT_EVIDENCE,
        ),
    )
    assert clarify.answer_mode is AnswerMode.CLARIFY
    assert clarify.clarification_question.count("？") == 0
    assert insufficient.answer_mode is AnswerMode.INSUFFICIENT_EVIDENCE


def test_conflicting_evidence_cannot_be_marked_sufficient() -> None:
    result = SufficiencyDecision(
        sufficient=True,
        supported_claims=(),
        unsupported_claims=(),
        conflicts=("制度 A 与制度 B 冲突",),
        recommended_mode=AnswerMode.COMPANY_KNOWLEDGE,
    )
    assert result.sufficient is False
    assert result.recommended_mode is AnswerMode.INSUFFICIENT_EVIDENCE


def test_unrelated_unsupported_candidate_does_not_override_supported_answer() -> None:
    result = SufficiencyDecision(
        sufficient=True,
        supported_claims=(
            {"claim": "图中包含 Agent Harness 层", "supporting_chunk_ids": [CHUNK_ID]},
        ),
        unsupported_claims=("不能把 Java 的模块层级当成 Agent 架构层级",),
        conflicts=(),
        recommended_mode=AnswerMode.COMPANY_KNOWLEDGE,
    )
    assert result.sufficient is True


async def test_empty_evidence_uses_sufficiency_without_expanding_legacy_permission() -> (
    None
):
    gateway = Gateway(
        [
            SufficiencyDecision(
                sufficient=False,
                supported_claims=(),
                unsupported_claims=("缺少公司资料",),
                conflicts=(),
                recommended_mode=AnswerMode.INSUFFICIENT_EVIDENCE,
            )
        ]
    )
    result = await judge_sufficiency(gateway, "年假怎么申请？", ())
    assert not result.sufficient
    assert result.recommended_mode is AnswerMode.INSUFFICIENT_EVIDENCE
    assert gateway.stages == ["sufficiency"]


async def test_sufficiency_cannot_reference_unprovided_chunk() -> None:
    gateway = Gateway(
        [
            SufficiencyDecision(
                sufficient=True,
                supported_claims=(
                    {
                        "claim": "事实",
                        "supporting_chunk_ids": [
                            UUID("90000000-0000-0000-0000-000000000099")
                        ],
                    },
                ),
                unsupported_claims=(),
                conflicts=(),
                recommended_mode=AnswerMode.COMPANY_KNOWLEDGE,
            )
        ]
    )
    result = await judge_sufficiency(gateway, "年假怎么申请？", evidence())
    assert not result.sufficient
