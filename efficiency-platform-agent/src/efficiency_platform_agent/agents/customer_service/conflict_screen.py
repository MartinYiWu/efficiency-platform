"""对最终父证据集合逐对核验跨文档冲突。"""

import html
import re
from itertools import combinations
from uuid import UUID

from .intent import StructuredStageGateway
from .state import (
    ConflictPair,
    ConflictScreen,
    EvidenceContractError,
    ParentEvidence,
    StrictModel,
)


class ConflictResponse(StrictModel):
    pairs: tuple[ConflictPair, ...]


def _source_text(value: str) -> str:
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!<>])", r"\1", html.unescape(value))


async def screen_conflicts(
    parents: tuple[ParentEvidence, ...],
    *,
    question: str,
    gateway: StructuredStageGateway,
    members: set[tuple[UUID, UUID, UUID, UUID]],
    stage_bound: bool,
) -> ConflictScreen:
    decisions = []
    errors = []
    if any(
        (p.knowledge_base_id, p.document_id, p.document_version_id, p.index_release_id)
        not in members
        for p in parents
    ):
        return ConflictScreen(errors=("CONFLICT_INDEX_MEMBER_INVALID",), blocked=True)
    for left, right in combinations(parents, 2):
        if (left.knowledge_base_id, left.document_id) == (
            right.knowledge_base_id,
            right.document_id,
        ):
            continue
        if not stage_bound:
            errors.append("PROMPT_STAGE_NOT_BOUND")
            break
        try:
            response = await gateway.complete(
                "conflict_screen",
                {
                    "question": question,
                    "evidence": [p.model_dump(mode="json") for p in (left, right)],
                },
                ConflictResponse,
            )
            response = ConflictResponse.model_validate(response.model_dump())
            if len(response.pairs) != 1:
                raise EvidenceContractError("CONFLICT_PAIR_COVERAGE_INVALID")
            pair = response.pairs[0]
            if (pair.left_parent_id, pair.right_parent_id) != (
                left.parent_id,
                right.parent_id,
            ):
                raise EvidenceContractError("CONFLICT_PARENT_ID_INVALID")
            if (
                not pair.left_quote.strip()
                or not pair.right_quote.strip()
                or _source_text(pair.left_quote) not in _source_text(left.content)
                or _source_text(pair.right_quote) not in _source_text(right.content)
            ):
                raise EvidenceContractError("CONFLICT_QUOTE_INVALID")
            if not pair.reason.strip():
                raise EvidenceContractError("CONFLICT_REASON_INVALID")
            decisions.append(pair)
        except Exception as error:  # noqa: BLE001
            errors.append(getattr(error, "code", "CONFLICT_CONTRACT_INVALID"))
    return ConflictScreen(
        pairs=tuple(decisions),
        errors=tuple(errors),
        blocked=bool(errors) or any(p.verdict != "NO_CONFLICT" for p in decisions),
    )
