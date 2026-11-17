"""对最终父证据集合逐对核验跨文档冲突。"""

import asyncio
import html
import logging
import re
from itertools import combinations
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool, ValidationError

from efficiency_platform_agent.core.execution_control import MAX_RUN_CALLS
from efficiency_platform_agent.core.paid_budget import PaidBudgetError

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
    batch_enabled: bool = False,
) -> ConflictScreen:
    decisions = []
    errors = []
    if any(
        (p.knowledge_base_id, p.document_id, p.document_version_id, p.index_release_id)
        not in members
        for p in parents
    ):
        return ConflictScreen(errors=("CONFLICT_INDEX_MEMBER_INVALID",), blocked=True)
    unique: dict[UUID, ParentEvidence] = {}
    for parent in parents:
        if parent.parent_id in unique and unique[parent.parent_id] != parent:
            return ConflictScreen(
                errors=("CONFLICT_SOURCE_IDENTITY_INVALID",), blocked=True
            )
        unique[parent.parent_id] = parent
    parents = tuple(unique.values())
    pairs = [
        (left, right)
        for left, right in combinations(parents, 2)
        if (left.knowledge_base_id, left.document_id)
        != (right.knowledge_base_id, right.document_id)
    ]
    if pairs and not stage_bound:
        return ConflictScreen(errors=("PROMPT_STAGE_NOT_BOUND",), blocked=True)
    units = (len(pairs) + 2) // 3 if batch_enabled else len(pairs)
    if units > MAX_RUN_CALLS:
        raise PaidBudgetError(
            "AGENT_WORK_LIMIT_EXCEEDED", "冲突核验工作量超过单任务上限"
        )

    async def gather_checks(items, check):
        iterator = iter(enumerate(items))
        results = [None] * len(items)

        async def worker():
            for index, item in iterator:
                results[index] = await check(item)

        tasks = [asyncio.create_task(worker()) for _ in range(min(8, len(items)))]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return results

    async def check_batch(batch: list[tuple[ParentEvidence, ParentEvidence]]):
        try:
            sources = {p.parent_id: p for pair in batch for p in pair}
            response = await gateway.complete(
                "conflict_screen",
                {
                    "question": question,
                    "evidence": [p.model_dump(mode="json") for p in sources.values()],
                    "comparison_pairs": [
                        {
                            "left_parent_id": str(left.parent_id),
                            "right_parent_id": str(right.parent_id),
                        }
                        for left, right in batch
                    ],
                },
                ConflictResponse,
            )
            response = ConflictResponse.model_validate(response.model_dump())
            expected = {
                (str(left.parent_id), str(right.parent_id)) for left, right in batch
            }
            drafts = {
                (str(p.left_parent_id), str(p.right_parent_id)): p
                for p in response.pairs
            }
            if (
                len(response.pairs) != len(batch)
                or len(drafts) != len(batch)
                or set(drafts) != expected
            ):
                raise EvidenceContractError("CONFLICT_PAIR_COVERAGE_INVALID")
            verified = []
            for left, right in batch:
                draft = drafts[(str(left.parent_id), str(right.parent_id))]
                if (
                    not draft.left_quote.strip()
                    or not draft.right_quote.strip()
                    or _source_text(draft.left_quote) not in _source_text(left.content)
                    or _source_text(draft.right_quote)
                    not in _source_text(right.content)
                ):
                    raise EvidenceContractError("CONFLICT_QUOTE_INVALID")
                if not draft.reason.strip():
                    raise EvidenceContractError("CONFLICT_REASON_INVALID")
                verified.append(
                    ConflictPair(
                        left_parent_id=left.parent_id,
                        right_parent_id=right.parent_id,
                        same_scope=draft.same_scope,
                        verdict=draft.verdict,
                        left_quote=draft.left_quote,
                        right_quote=draft.right_quote,
                        reason=draft.reason,
                    )
                )
            return tuple(verified), None
        except (EvidenceContractError, ValidationError) as error:
            code = getattr(error, "code", "CONFLICT_CONTRACT_INVALID")
            return (), code

    if batch_enabled:
        started = asyncio.get_running_loop().time()
        batches = [pairs[index : index + 3] for index in range(0, len(pairs), 3)]
        for verified, error in await gather_checks(batches, check_batch):
            decisions.extend(verified)
            if error is not None:
                errors.append(error)
        logger.info(
            "event=customer_service_conflict_batches pair_count=%s batch_count=%s elapsed_ms=%.0f",
            len(pairs),
            len(batches),
            (asyncio.get_running_loop().time() - started) * 1000,
        )
        return ConflictScreen(
            pairs=tuple(decisions),
            errors=tuple(errors),
            blocked=bool(errors) or any(p.verdict != "NO_CONFLICT" for p in decisions),
        )

    async def check_pair(left: ParentEvidence, right: ParentEvidence):
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
            draft = response.pairs[0]
            if (
                not draft.left_quote.strip()
                or not draft.right_quote.strip()
                or _source_text(draft.left_quote) not in _source_text(left.content)
                or _source_text(draft.right_quote) not in _source_text(right.content)
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
        except (EvidenceContractError, ValidationError) as error:
            code = getattr(error, "code", "CONFLICT_CONTRACT_INVALID")
            return None, code

    for pair, error in await gather_checks(pairs, lambda pair: check_pair(*pair)):
        if pair is not None:
            decisions.append(pair)
        if error is not None:
            errors.append(error)
    return ConflictScreen(
        pairs=tuple(decisions),
        errors=tuple(errors),
        blocked=bool(errors) or any(p.verdict != "NO_CONFLICT" for p in decisions),
    )
