"""五种回答模式生成与一次结构修复。"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import ValidationError

from .answer_stream import AnswerSectionStream
from .citations import CitationGuardError, validate_citation_closure
from .intent import StructuredStageGateway
from .model_gateway import StructuredModelError
from .state import (
    AnswerMode,
    CustomerServiceAnswer,
    Evidence,
    EvidencePack,
    HistoryMessage,
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
    evidence: tuple[Evidence, ...] | EvidencePack,
    sufficiency: SufficiencyDecision | None,
    history: tuple[HistoryMessage, ...] = (),
    on_block: Callable[[str, AnswerMode], None] | None = None,
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
        "evidence": evidence.model_input()
        if isinstance(evidence, EvidencePack)
        else [item.model_dump(mode="json") for item in evidence],
        "sufficiency": None
        if sufficiency is None
        else sufficiency.model_dump(mode="json"),
    }
    if isinstance(evidence, EvidencePack):
        from .citations import validate_evidence_pack

        try:
            validate_evidence_pack(evidence)
        except CitationGuardError:
            return insufficient_answer("冻结证据未通过原文校验。")
        if evidence.blocked:
            return insufficient_answer("冻结证据存在冲突或超出完整原文预算。")
        value["history"] = [h.model_dump(mode="json") for h in history]
    emitted: list[str] = []
    try:
        stream = getattr(gateway, "stream_complete", None)
        if (
            on_block is not None
            and isinstance(evidence, EvidencePack)
            and stage in {"answer_company", "answer_mixed"}
            and callable(stream)
        ):
            mode = (
                AnswerMode.COMPANY_KNOWLEDGE
                if stage == "answer_company"
                else AnswerMode.MIXED
            )

            def emit(block: str) -> None:
                on_block(block, mode)
                emitted.append(block)

            parser = AnswerSectionStream(evidence, emit)
            answer = await stream(stage, value, CustomerServiceAnswer, parser.feed)
        else:
            answer = await gateway.complete(stage, value, CustomerServiceAnswer)
        validate_citation_closure(answer, evidence)
        return answer
    except StructuredModelError as error:
        if not emitted and error.code in {
            "MODEL_RESPONSE_INVALID",
            "PROVIDER_RESPONSE_TRUNCATED",
        }:
            answer = await gateway.complete(stage, value, CustomerServiceAnswer)
            validate_citation_closure(answer, evidence)
            return answer
        if (
            not isinstance(evidence, EvidencePack)
            or error.code != "MODEL_INPUT_BUDGET_EXCEEDED"
        ):
            raise
        return insufficient_answer("完整模型输入超过预算。")
    except (ValidationError, CitationGuardError, ValueError) as first_error:
        if emitted:
            raise StructuredModelError(
                "STREAM_ANSWER_INVALID", "流式回答未通过完整校验"
            ) from first_error
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
        except StructuredModelError as error:
            if (
                not isinstance(evidence, EvidencePack)
                or error.code != "MODEL_INPUT_BUDGET_EXCEEDED"
            ):
                raise
            return insufficient_answer("完整模型输入超过预算。")
        except (ValidationError, CitationGuardError, ValueError):
            return insufficient_answer(
                "模型回答未通过结构和引用校验，已停止输出公司事实。"
            )


__all__ = ["generate_answer", "insufficient_answer"]
