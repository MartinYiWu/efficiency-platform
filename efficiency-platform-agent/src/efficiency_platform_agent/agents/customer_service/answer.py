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


def select_answer_mode(
    intent: IntentDecision, sufficiency: SufficiencyDecision | None
) -> AnswerMode:
    if intent.intent_type is IntentType.AMBIGUOUS_QUERY:
        return AnswerMode.CLARIFY
    if intent.intent_type is IntentType.GENERAL_QUERY:
        return AnswerMode.GENERAL_ADVICE
    if (
        sufficiency is None
        or sufficiency.conflicts
        or sufficiency.evidence_status == "CONFLICT"
    ):
        return AnswerMode.INSUFFICIENT_EVIDENCE
    if sufficiency.evidence_status is None:
        if not sufficiency.sufficient:
            return AnswerMode.INSUFFICIENT_EVIDENCE
        return (
            AnswerMode.MIXED
            if intent.intent_type is IntentType.MIXED_QUERY
            else AnswerMode.COMPANY_KNOWLEDGE
        )
    company_allowed = bool(sufficiency.supported_claims) and (
        sufficiency.evidence_status == "PARTIAL"
        or (sufficiency.evidence_status == "SUFFICIENT" and sufficiency.sufficient)
    )
    general_allowed = sufficiency.general_advice_allowed and bool(
        sufficiency.general_advice_scope
    )
    recommended = sufficiency.recommended_mode
    if recommended is AnswerMode.MIXED and company_allowed and general_allowed:
        return AnswerMode.MIXED
    if recommended is AnswerMode.COMPANY_KNOWLEDGE and company_allowed:
        return AnswerMode.COMPANY_KNOWLEDGE
    if recommended in {AnswerMode.GENERAL_ADVICE, AnswerMode.MIXED} and general_allowed:
        return AnswerMode.GENERAL_ADVICE
    return AnswerMode.INSUFFICIENT_EVIDENCE


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
    mode = select_answer_mode(intent, sufficiency)
    if mode is AnswerMode.CLARIFY:
        return clarification_answer(intent)
    original_evidence = evidence
    if isinstance(evidence, EvidencePack):
        from .citations import validate_evidence_pack

        try:
            validate_evidence_pack(evidence)
        except CitationGuardError:
            return insufficient_answer("冻结证据未通过原文校验。")
        if evidence.blocked:
            if evidence.conflict_screen and evidence.conflict_screen.blocked:
                return insufficient_answer(
                    "公司资料存在冲突或尚未完成有效核验，暂时不能确认相关规则。"
                )
            if any(
                "BUDGET" in reason or "TOO_LARGE" in reason
                for reason in evidence.block_reasons
            ):
                return insufficient_answer(
                    "完整公司原文超出模型预算，暂时不能可靠回答。"
                )
            return insufficient_answer(
                "冻结公司证据未完成原文核验，暂时不能确认相关规则。"
            )
    if mode is AnswerMode.INSUFFICIENT_EVIDENCE:
        if sufficiency is not None:
            if sufficiency.conflicts or sufficiency.evidence_status == "CONFLICT":
                return insufficient_answer(
                    "公司资料存在冲突或尚未完成有效核验，暂时不能确认相关规则。"
                )
            if "完整模型输入超过预算" in sufficiency.unsupported_claims:
                return insufficient_answer("完整模型输入超过预算，暂时不能可靠回答。")
            if "充分性判断引用了未入选的证据" in sufficiency.unsupported_claims:
                return insufficient_answer(
                    "充分性判断未通过引用校验，已停止输出公司事实。"
                )
            if "冻结公司证据未通过原文核验" in sufficiency.unsupported_claims:
                return insufficient_answer(
                    "冻结公司证据未通过原文核验，暂时不能确认相关规则。"
                )
            if sufficiency.evidence_status == "PARTIAL":
                return insufficient_answer(
                    "现有公司依据只能覆盖部分事项，尚不足以回答本次问题。"
                )
        return insufficient_answer(
            "现有公司资料尚未确认所需规则，也没有适用的一般补充范围。"
        )
    stage = {
        AnswerMode.GENERAL_ADVICE: "answer_general",
        AnswerMode.MIXED: "answer_mixed",
        AnswerMode.COMPANY_KNOWLEDGE: "answer_company",
    }[mode]
    if sufficiency is not None and sufficiency.evidence_status == "PARTIAL":
        allowed = {
            chunk_id
            for claim in sufficiency.supported_claims
            for chunk_id in claim.supporting_chunk_ids
        }
        entries = evidence.entries if isinstance(evidence, EvidencePack) else evidence
        selected = tuple(item for item in entries if item.chunk_id in allowed)
        evidence = (
            evidence.model_copy(update={"entries": selected})
            if isinstance(evidence, EvidencePack)
            else selected
        )
    if mode is AnswerMode.GENERAL_ADVICE:
        evidence = ()
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
    if isinstance(original_evidence, EvidencePack):
        value["history"] = [h.model_dump(mode="json") for h in history]
    emitted: list[str] = []

    async def complete(stage_key: str, input_value: object) -> CustomerServiceAnswer:
        stream = getattr(gateway, "stream_complete", None)
        parser = None
        received_content = False
        if on_block is not None and callable(stream):

            def emit(block: str) -> None:
                on_block(block, mode)
                emitted.append(block)

            parser = AnswerSectionStream(evidence, emit, expected_mode=mode)

            def feed(content: str) -> None:
                nonlocal received_content
                received_content = True
                parser.feed(content)

            answer = await stream(stage_key, input_value, CustomerServiceAnswer, feed)
        else:
            answer = await gateway.complete(
                stage_key, input_value, CustomerServiceAnswer
            )
        if answer.answer_mode is not mode:
            raise ValueError("模型回答模式与已批准模式不一致")
        validate_citation_closure(answer, evidence)
        if parser is not None and received_content:
            parser.finish(answer)
        return answer

    try:
        return await complete(stage, value)
    except StructuredModelError as error:
        if not emitted and error.code in {
            "MODEL_RESPONSE_INVALID",
            "PROVIDER_RESPONSE_TRUNCATED",
        }:
            return await complete(stage, value)
        if emitted:
            raise
        if (
            not isinstance(original_evidence, EvidencePack)
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
            return await complete("answer_repair", repair_input)
        except StructuredModelError as error:
            if (
                emitted
                or not isinstance(original_evidence, EvidencePack)
                or error.code != "MODEL_INPUT_BUDGET_EXCEEDED"
            ):
                raise
            return insufficient_answer("完整模型输入超过预算。")
        except (ValidationError, CitationGuardError, ValueError):
            if emitted:
                raise StructuredModelError(
                    "STREAM_ANSWER_INVALID", "流式回答未通过完整校验"
                )
            return insufficient_answer(
                "模型回答未通过结构和引用校验，已停止输出公司事实。"
            )


__all__ = ["generate_answer", "insufficient_answer", "select_answer_mode"]
