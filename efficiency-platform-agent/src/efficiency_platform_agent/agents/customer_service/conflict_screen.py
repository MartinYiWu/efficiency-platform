"""对最终父证据集合逐对核验跨文档冲突。"""

import asyncio
import html
import logging
import re
from itertools import combinations
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool

from .intent import StructuredStageGateway
from .state import (
    ConflictPair,
    ConflictScreen,
    EvidenceContractError,
    ParentEvidence,
    StrictModel,
)

logger = logging.getLogger("efficiency_platform_agent.execution")


class ConflictPairDraft(StrictModel):
    # 模型回显的 ID 不作身份依据；输入证据对和逐字摘录由程序绑定与核验。
    left_parent_id: str | UUID
    right_parent_id: str | UUID
    same_scope: StrictBool
    verdict: Literal["CONFLICT", "NO_CONFLICT", "UNCERTAIN"]
    left_quote: str = Field(min_length=1)
    right_quote: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ConflictResponse(StrictModel):
    pairs: tuple[ConflictPairDraft, ...]


def _source_text(value: str) -> str:
    unescaped = re.sub(r"\\([\\`*_{}\[\]()#+\-.!<>])", r"\1", html.unescape(value))
    return unescaped.replace("**", "").replace("__", "").replace("`", "")


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
    pairs = [
        (left, right)
        for left, right in combinations(parents, 2)
        if (left.knowledge_base_id, left.document_id)
        != (right.knowledge_base_id, right.document_id)
    ]
    if pairs and not stage_bound:
        return ConflictScreen(errors=("PROMPT_STAGE_NOT_BOUND",), blocked=True)
    limit = asyncio.Semaphore(8)

    async def check_pair(left: ParentEvidence, right: ParentEvidence):
        async with limit:
            for attempt in range(2):
                try:
                    response = await gateway.complete(
                        "conflict_screen",
                        {
                            "question": question,
                            "evidence": [
                                p.model_dump(mode="json") for p in (left, right)
                            ],
                        },
                        ConflictResponse,
                    )
                    response = ConflictResponse.model_validate(response.model_dump())
                    if len(response.pairs) != 1:
                        raise EvidenceContractError("CONFLICT_PAIR_COVERAGE_INVALID")
                    draft = response.pairs[0]
                    if (
                        not draft.left_quote.strip()
                        or not draft.right_quote.strip()
                        or _source_text(draft.left_quote)
                        not in _source_text(left.content)
                        or _source_text(draft.right_quote)
                        not in _source_text(right.content)
                    ):
                        raise EvidenceContractError("CONFLICT_QUOTE_INVALID")
                    if not draft.reason.strip():
                        raise EvidenceContractError("CONFLICT_REASON_INVALID")
                    pair = ConflictPair(
                        left_parent_id=left.parent_id,
                        right_parent_id=right.parent_id,
                        same_scope=draft.same_scope,
                        verdict=draft.verdict,
                        left_quote=draft.left_quote,
                        right_quote=draft.right_quote,
                        reason=draft.reason,
                    )
                    return pair, None
                except Exception as error:  # noqa: BLE001
                    code = getattr(error, "code", "CONFLICT_CONTRACT_INVALID")
                    if attempt == 0:
                        logger.warning(
                            "event=customer_service_conflict_retry code=%s attempt=%s left_parent_id=%s right_parent_id=%s",
                            code,
                            attempt + 1,
                            left.parent_id,
                            right.parent_id,
                        )
                    else:
                        return None, code

    for pair, error in await asyncio.gather(
        *(check_pair(left, right) for left, right in pairs)
    ):
        if pair is not None:
            decisions.append(pair)
        if error is not None:
            errors.append(error)
    return ConflictScreen(
        pairs=tuple(decisions),
        errors=tuple(errors),
        blocked=bool(errors) or any(p.verdict != "NO_CONFLICT" for p in decisions),
    )
