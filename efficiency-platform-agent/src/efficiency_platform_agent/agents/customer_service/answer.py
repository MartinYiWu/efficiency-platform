"""五种回答模式生成与一次结构修复。"""

from __future__ import annotations

from pydantic import ValidationError

from .citations import CitationGuardError, validate_citation_closure
from .intent import StructuredStageGateway
from .state import (
    AnswerMode,
    CustomerServiceAnswer,
    Evidence,
    IntentDecision,
    IntentType,
    SufficiencyDecision,
)


def clarification_answer(decision: IntentDecision) -> CustomerServiceAnswer:
    return CustomerServiceAnswer(
        contract_version="customer-service-answer/1",
        answer_mode=AnswerMode.CLARIFY,
        clarification_question=f"请补充{decision.missing_field}，我再为你准确查询。",
    )


def insufficient_answer(reason: str) -> CustomerServiceAnswer:
    return CustomerServiceAnswer(
        contract_version="customer-service-answer/1",
        answer_mode=AnswerMode.INSUFFICIENT_EVIDENCE,
        insufficiency_reason=reason,
    )


async def generate_answer(
    gateway: StructuredStageGateway,
    *,
    question: str,
    intent: IntentDecision,
    evidence: tuple[Evidence, ...],
    sufficiency: SufficiencyDecision | None,
) -> CustomerServiceAnswer:
    if intent.intent_type is IntentType.AMBIGUOUS_QUERY:
        return clarification_answer(intent)
    if intent.intent_type is IntentType.GENERAL_QUERY:
        stage = "answer_general"
    elif sufficiency is None or not sufficiency.sufficient:
        return insufficient_answer("当前已发布公司资料不足以支持可靠回答。")
    elif intent.intent_type is IntentType.MIXED_QUERY:
        stage = "answer_mixed"
    else:
        stage = "answer_company"
    value = {
        "question": question,
        "intent": intent.model_dump(mode="json"),
        "evidence": [item.model_dump(mode="json") for item in evidence],
        "sufficiency": None
        if sufficiency is None
        else sufficiency.model_dump(mode="json"),
    }
    try:
        answer = await gateway.complete(stage, value, CustomerServiceAnswer)
        validate_citation_closure(answer, evidence)
        return answer
    except (ValidationError, CitationGuardError, ValueError) as first_error:
        repair_input = {
            "original_input": value,
            "validation_error": str(first_error),
        }
        try:
            answer = await gateway.complete(
                "answer_repair", repair_input, CustomerServiceAnswer
            )
            validate_citation_closure(answer, evidence)
            return answer
        except (ValidationError, CitationGuardError, ValueError):
            return insufficient_answer(
                "模型回答未通过结构和引用校验，已停止输出公司事实。"
            )


__all__ = ["generate_answer", "insufficient_answer"]
