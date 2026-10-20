"""智能客服证据充分性阶段。"""

from __future__ import annotations

from .intent import StructuredStageGateway
from .state import Evidence, SufficiencyDecision


async def judge_sufficiency(
    gateway: StructuredStageGateway,
    question: str,
    evidence: tuple[Evidence, ...],
) -> SufficiencyDecision:
    return await gateway.complete(
        "sufficiency",
        {
            "question": question,
            "evidence": [item.model_dump(mode="json") for item in evidence],
        },
        SufficiencyDecision,
    )


__all__ = ["judge_sufficiency"]
