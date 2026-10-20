"""独立 CustomerServiceGraph；不依赖运营助手。"""

from __future__ import annotations

from dataclasses import dataclass

from .answer import generate_answer
from .intent import StructuredStageGateway, classify_intent
from .release_bundle import CustomerServiceReleaseBundle
from .renderer import render_answer
from .retrieval import CustomerServiceRetrieval
from .state import CustomerServiceRunRequest, Evidence, IntentType, RenderedAnswer
from .sufficiency import judge_sufficiency


@dataclass(frozen=True, slots=True)
class GraphResult:
    rendered: RenderedAnswer
    stage_summaries: tuple[tuple[str, str], ...]
    evidence: tuple[Evidence, ...] = ()


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
        sufficiency = None
        summaries: list[tuple[str, str]] = [
            ("intent", f"已识别 {intent.intent_type.value}")
        ]
        if intent.intent_type in {IntentType.COMPANY_QUERY, IntentType.MIXED_QUERY}:
            evidence = await self.retrieval.search(
                tenant_id=request.tenant_id,
                question=intent.normalized_question,
                gateway=gateway,
                bundle=bundle,
            )
            summaries.append(("retrieval", f"已重排 {len(evidence)} 条候选证据"))
            sufficiency = await judge_sufficiency(
                gateway, intent.normalized_question, evidence
            )
            summaries.append(
                ("sufficiency", "证据充分" if sufficiency.sufficient else "证据不足")
            )
        answer = await generate_answer(
            gateway,
            question=intent.normalized_question,
            intent=intent,
            evidence=evidence,
            sufficiency=sufficiency,
        )
        return GraphResult(
            rendered=render_answer(answer, evidence),
            stage_summaries=tuple(summaries),
            evidence=evidence,
        )


__all__ = ["CustomerServiceGraph", "GraphResult"]
