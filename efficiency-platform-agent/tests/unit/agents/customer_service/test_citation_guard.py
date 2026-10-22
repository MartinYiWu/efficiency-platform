from __future__ import annotations

from hashlib import sha256
from uuid import UUID

import pytest

from efficiency_platform_agent.agents.customer_service.citations import (
    CitationGuardError,
    freeze_citations,
    validate_citation_closure,
)
from efficiency_platform_agent.agents.customer_service.state import (
    AnswerMode,
    CompanyParagraph,
    CompanySection,
    CustomerServiceAnswer,
)
from tests.unit.agents.customer_service.test_answer_modes import CHUNK_ID, evidence


def company_answer(chunk_id: UUID) -> CustomerServiceAnswer:
    return CustomerServiceAnswer(
        contract_version="customer-service-answer/1",
        answer_mode=AnswerMode.COMPANY_KNOWLEDGE,
        company_sections=(
            CompanySection(
                title="制度",
                paragraphs=(
                    CompanyParagraph(text="事实", supporting_chunk_ids=(chunk_id,)),
                ),
            ),
        ),
    )


def test_rejects_invented_chunk_id() -> None:
    with pytest.raises(CitationGuardError):
        validate_citation_closure(
            company_answer(UUID("90000000-0000-0000-0000-000000000099")), evidence()
        )


def test_accepts_only_current_candidate_chunk() -> None:
    validate_citation_closure(company_answer(CHUNK_ID), evidence())


def test_parent_citation_quotes_complete_clause_and_keeps_child_anchor() -> None:
    child_text = "例外：试用期员工不适用。"
    parent_text = "员工可申请假期。\n" + child_text
    item = evidence()[0].model_copy(
        update={
            "parent_id": UUID("90000000-0000-0000-0000-000000000088"),
            "content": parent_text,
            "content_hash": sha256(parent_text.encode()).hexdigest(),
            "hit_content": child_text,
            "hit_content_hash": sha256(child_text.encode()).hexdigest(),
            "hit_start_offset": len("员工可申请假期。\n"),
            "hit_end_offset": len(parent_text),
        }
    )
    citations = freeze_citations(company_answer(CHUNK_ID), (item,))
    assert citations[0].chunk_id == CHUNK_ID
    assert citations[0].quoted_text == parent_text
    assert citations[0].content_hash == sha256(parent_text.encode()).hexdigest()


def test_rejects_child_quote_outside_parent() -> None:
    item = evidence()[0].model_copy(
        update={
            "parent_id": UUID("90000000-0000-0000-0000-000000000088"),
            "content": "员工可申请假期。",
            "hit_content": "试用期员工不适用",
            "hit_content_hash": sha256("试用期员工不适用".encode()).hexdigest(),
            "hit_start_offset": 0,
            "hit_end_offset": 9,
        }
    )
    with pytest.raises(CitationGuardError):
        validate_citation_closure(company_answer(CHUNK_ID), (item,))
