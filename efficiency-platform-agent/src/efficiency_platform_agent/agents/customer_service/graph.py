"""独立 CustomerServiceGraph；不依赖运营助手。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Literal

from .answer import generate_answer
from .evidence_assembly import assemble_evidence, build_evidence_pack
from .intent import StructuredStageGateway, classify_intent
from .release_bundle import CustomerServiceReleaseBundle
from .renderer import render_answer
from .retrieval import CustomerServiceRetrieval, RetrievalTrace
from .state import (
    AnswerMode,
    CustomerServiceRunRequest,
    Evidence,
    EvidencePack,
    IntentType,
    RenderedAnswer,
    SufficiencyDecision,
)
from .sufficiency import judge_sufficiency

logger = logging.getLogger("efficiency_platform_agent.execution")


@dataclass(frozen=True, slots=True)
class GraphResult:
    rendered: RenderedAnswer
    stage_summaries: tuple[tuple[str, str], ...]
    evidence: tuple[Evidence, ...] = ()
    retrieval_trace: RetrievalTrace | None = None
    sufficiency: SufficiencyDecision | None = None
    evidence_pack: EvidencePack | None = None


class CustomerServiceGraph:
    def __init__(self, retrieval: CustomerServiceRetrieval) -> None:
        self.retrieval = retrieval

    async def run(
        self,
        request: CustomerServiceRunRequest,
        bundle: CustomerServiceReleaseBundle,
        gateway: StructuredStageGateway,
        on_answer_block: Callable[[str, AnswerMode], None] | None = None,
        on_stage: Callable[[str, Literal["STARTED", "COMPLETED"]], None] | None = None,
        on_conversation_title: Callable[[str], None] | None = None,
    ) -> GraphResult:
        started = perf_counter()
        intent = await classify_intent(
            gateway, request, rewrite_query_limit=bundle.rag_policy.rewrite_query_limit
        )
        if (
            not request.history
            and intent.conversation_title
            and on_conversation_title is not None
        ):
            on_conversation_title(intent.conversation_title)
        logger.info(
            "event=customer_service_stage_timing conversation_id=%s stage=intent elapsed_ms=%.0f",
            request.conversation_id,
            (perf_counter() - started) * 1000,
        )
        if on_stage is not None:
            on_stage("intent", "COMPLETED")
        evidence: tuple[Evidence, ...] = ()
        retrieval_trace = None
        sufficiency = None
        evidence_pack = None
        summaries: list[tuple[str, str]] = [
            ("intent", f"已识别 {intent.intent_type.value}")
        ]
        if intent.intent_type in {IntentType.COMPANY_QUERY, IntentType.MIXED_QUERY}:
            if on_stage is not None:
                on_stage("retrieval", "STARTED")
            retrieval_trace = await self.retrieval.search(
                tenant_id=request.tenant_id,
                question=intent.normalized_question,
                gateway=gateway,
                bundle=bundle,
                **(
                    {"planned_queries": intent.retrieval_queries}
                    if intent.retrieval_queries
                    else {}
                ),
            )
            logger.info(
                "event=customer_service_stage_timing conversation_id=%s stage=retrieval elapsed_ms=%.0f",
                request.conversation_id,
                (perf_counter() - started) * 1000,
            )
            if on_stage is not None:
                on_stage("retrieval", "COMPLETED")
            evidence = (
                retrieval_trace.assembly.selected
                if retrieval_trace.assembly is not None
                else retrieval_trace.reranked_evidence
            )
            summaries.append(("retrieval", f"已重排 {len(evidence)} 条候选证据"))
            if on_stage is not None:
                on_stage("verification", "STARTED")
            if bundle.contract_version.endswith("/2"):
                assembly = retrieval_trace.assembly or assemble_evidence(
                    (),
                    (),
                    context_token_limit=bundle.rag_policy.context_token_limit,
                    reserved_tokens=0,
                )
                evidence_pack = await build_evidence_pack(
                    assembly,
                    bundle=bundle,
                    gateway=gateway,
                    question=intent.normalized_question,
                    history=request.history,
                    conflict_screen=retrieval_trace.conflict_screen,
                    children=retrieval_trace.reranked_evidence,
                    intent=intent,
                )
                logger.info(
                    "event=customer_service_stage_timing conversation_id=%s stage=evidence_pack elapsed_ms=%.0f",
                    request.conversation_id,
                    (perf_counter() - started) * 1000,
                )
                retrieval_trace = replace(retrieval_trace, evidence_pack=evidence_pack)
                evidence = evidence_pack.entries
                if evidence_pack.model_policy != bundle.model_policy:
                    gateway = gateway.with_model_policy(evidence_pack.model_policy)
            sufficiency = await judge_sufficiency(
                gateway,
                intent.normalized_question,
                evidence_pack if evidence_pack is not None else evidence,
                conflict_screen=retrieval_trace.conflict_screen,
                history=request.history,
            )
            logger.info(
                "event=customer_service_stage_timing conversation_id=%s stage=sufficiency elapsed_ms=%.0f",
                request.conversation_id,
                (perf_counter() - started) * 1000,
            )
            if on_stage is not None:
                on_stage("verification", "COMPLETED")
            summaries.append(
                ("sufficiency", "证据充分" if sufficiency.sufficient else "证据不足")
            )
        if on_stage is not None:
            on_stage("answer", "STARTED")
        answer = await generate_answer(
            gateway,
            question=intent.normalized_question,
            intent=intent,
            evidence=evidence_pack if evidence_pack is not None else evidence,
            sufficiency=sufficiency,
            history=request.history,
            on_block=on_answer_block,
        )
        logger.info(
            "event=customer_service_stage_timing conversation_id=%s stage=answer elapsed_ms=%.0f",
            request.conversation_id,
            (perf_counter() - started) * 1000,
        )
        return GraphResult(
            rendered=render_answer(
                answer, evidence_pack if evidence_pack is not None else evidence
            ),
            stage_summaries=tuple(summaries),
            evidence=evidence,
            retrieval_trace=retrieval_trace,
            sufficiency=sufficiency,
            evidence_pack=evidence_pack,
        )


__all__ = ["CustomerServiceGraph", "GraphResult"]
