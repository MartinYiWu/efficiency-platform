"""独立 CustomerServiceGraph；不依赖运营助手。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .answer import generate_answer
from .evidence_assembly import assemble_evidence, build_evidence_pack
from .intent import StructuredStageGateway, classify_intent
from .release_bundle import CustomerServiceReleaseBundle
from .renderer import render_answer
from .retrieval import CustomerServiceRetrieval, RetrievalTrace
from .state import (
    CustomerServiceRunRequest,
    Evidence,
    EvidencePack,
    IntentType,
    RenderedAnswer,
    SufficiencyDecision,
)
from .sufficiency import judge_sufficiency


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
    ) -> GraphResult:
        intent = await classify_intent(gateway, request)
        evidence: tuple[Evidence, ...] = ()
        retrieval_trace = None
        sufficiency = None
        evidence_pack = None
        summaries: list[tuple[str, str]] = [
            ("intent", f"已识别 {intent.intent_type.value}")
        ]
        if intent.intent_type in {IntentType.COMPANY_QUERY, IntentType.MIXED_QUERY}:
            retrieval_trace = await self.retrieval.search(
                tenant_id=request.tenant_id,
                question=intent.normalized_question,
                gateway=gateway,
                bundle=bundle,
            )
            evidence = (
                retrieval_trace.assembly.selected
                if retrieval_trace.assembly is not None
                else retrieval_trace.reranked_evidence
            )
            summaries.append(("retrieval", f"已重排 {len(evidence)} 条候选证据"))
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
            summaries.append(
                ("sufficiency", "证据充分" if sufficiency.sufficient else "证据不足")
            )
        answer = await generate_answer(
            gateway,
            question=intent.normalized_question,
            intent=intent,
            evidence=evidence_pack if evidence_pack is not None else evidence,
            sufficiency=sufficiency,
            history=request.history,
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
