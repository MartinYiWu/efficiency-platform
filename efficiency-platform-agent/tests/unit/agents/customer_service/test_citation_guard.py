from __future__ import annotations

from uuid import UUID

import pytest

from efficiency_platform_agent.agents.customer_service.citations import (
    CitationGuardError,
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
        company_sections=(CompanySection(title="制度", paragraphs=(CompanyParagraph(text="事实", supporting_chunk_ids=(chunk_id,)),)),),
    )


def test_rejects_invented_chunk_id() -> None:
    with pytest.raises(CitationGuardError):
        validate_citation_closure(company_answer(UUID("90000000-0000-0000-0000-000000000099")), evidence())


def test_accepts_only_current_candidate_chunk() -> None:
    validate_citation_closure(company_answer(CHUNK_ID), evidence())
