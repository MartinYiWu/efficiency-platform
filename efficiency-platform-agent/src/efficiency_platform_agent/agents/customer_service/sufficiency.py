"""智能客服证据充分性阶段。"""

from __future__ import annotations

from .conflict_screen import ConflictScreen
from .intent import StructuredStageGateway
from .state import AnswerMode, Evidence, SufficiencyDecision


async def judge_sufficiency(
    gateway: StructuredStageGateway,
    question: str,
    evidence: tuple[Evidence, ...],
    *,
    conflict_screen: ConflictScreen | None = None,
) -> SufficiencyDecision:
    if conflict_screen is not None and conflict_screen.blocked:
        return SufficiencyDecision(
            sufficient=False,
            supported_claims=(),
            unsupported_claims=(),
            conflicts=("公司资料存在冲突或尚未完成有效核验",),
            recommended_mode=AnswerMode.INSUFFICIENT_EVIDENCE,
        )
    if not evidence:
        return SufficiencyDecision(
            sufficient=False,
            supported_claims=(),
            unsupported_claims=("未检索到可用的完整公司条款",),
            conflicts=(),
            recommended_mode=AnswerMode.INSUFFICIENT_EVIDENCE,
        )
    decision = await gateway.complete(
        "sufficiency",
        {
            "question": question,
            "evidence": [item.model_dump(mode="json") for item in evidence],
        },
        SufficiencyDecision,
    )
    allowed = {item.chunk_id for item in evidence}
    if any(
        not set(claim.supporting_chunk_ids).issubset(allowed)
        for claim in decision.supported_claims
    ):
        return decision.model_copy(
            update={
                "sufficient": False,
                "recommended_mode": AnswerMode.INSUFFICIENT_EVIDENCE,
                "unsupported_claims": decision.unsupported_claims
                + ("充分性判断引用了未入选的证据",),
            }
        )
    return decision


__all__ = ["judge_sufficiency"]
