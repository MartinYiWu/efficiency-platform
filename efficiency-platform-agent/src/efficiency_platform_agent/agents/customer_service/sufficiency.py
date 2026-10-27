"""智能客服证据充分性阶段。"""

from __future__ import annotations

from .citations import validate_evidence_pack
from .conflict_screen import ConflictScreen
from .intent import StructuredStageGateway
from .model_gateway import StructuredModelError
from .state import (
    AnswerMode,
    Evidence,
    EvidencePack,
    HistoryMessage,
    SufficiencyDecision,
)


async def judge_sufficiency(
    gateway: StructuredStageGateway,
    question: str,
    evidence: tuple[Evidence, ...] | EvidencePack,
    *,
    conflict_screen: ConflictScreen | None = None,
    history: tuple[HistoryMessage, ...] = (),
) -> SufficiencyDecision:
    entries: tuple[Evidence, ...]
    if isinstance(evidence, EvidencePack):
        pack = evidence
        validate_evidence_pack(pack)
        entries = pack.entries
        conflict_screen = pack.conflict_screen
    else:
        pack = None
        entries = evidence
    if (pack is not None and pack.blocked) or (
        conflict_screen is not None and conflict_screen.blocked
    ):
        return SufficiencyDecision(
            sufficient=False,
            supported_claims=(),
            unsupported_claims=(),
            conflicts=("公司资料存在冲突或尚未完成有效核验",),
            recommended_mode=AnswerMode.INSUFFICIENT_EVIDENCE,
        )
    if not entries:
        return SufficiencyDecision(
            sufficient=False,
            supported_claims=(),
            unsupported_claims=("未检索到可用的完整公司条款",),
            conflicts=(),
            recommended_mode=AnswerMode.INSUFFICIENT_EVIDENCE,
        )
    try:
        decision = await gateway.complete(
            "sufficiency",
            {
                "question": question,
                "evidence": pack.model_input()
                if pack is not None
                else [item.model_dump(mode="json") for item in entries],
                **(
                    {"history": [h.model_dump(mode="json") for h in history]}
                    if pack is not None
                    else {}
                ),
            },
            SufficiencyDecision,
        )
    except StructuredModelError as error:
        if pack is None or error.code != "MODEL_INPUT_BUDGET_EXCEEDED":
            raise
        return SufficiencyDecision(
            sufficient=False,
            supported_claims=(),
            unsupported_claims=("完整模型输入超过预算",),
            conflicts=(),
            recommended_mode=AnswerMode.INSUFFICIENT_EVIDENCE,
        )
    allowed = {item.chunk_id for item in entries}
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
