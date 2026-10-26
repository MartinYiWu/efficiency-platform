"""同版同路径候选的相似筛选、等价校验与保守分组。"""

from __future__ import annotations

import asyncio
from hashlib import sha256
from itertools import combinations
from math import isfinite, sqrt
from typing import Literal
from uuid import UUID

from pydantic import Field, ValidationError

from .intent import StructuredStageGateway
from .model_gateway import StructuredModelError
from .state import Evidence, EvidenceContractError, ParentEvidence, StrictModel


class EquivalenceResult(StrictModel):
    left_chunk_id: UUID
    right_chunk_id: UUID
    verdict: Literal["EQUIVALENT", "DIFFERENT", "UNCERTAIN"]
    left_quote: str = Field(min_length=1)
    right_quote: str = Field(min_length=1)
    differing_conditions: tuple[str, ...]


class EquivalenceDecision(StrictModel):
    left: Evidence
    right: Evidence
    left_parent: ParentEvidence
    right_parent: ParentEvidence
    similarity: float
    reason: str
    result: EquivalenceResult | None = None
    retained_parent_id: UUID | None = None
    merged_chunk_ids: tuple[UUID, ...] = ()


def validate_parents(
    children: tuple[Evidence, ...], parents: tuple[ParentEvidence, ...]
) -> None:
    by_id = {p.parent_id: p for p in parents}
    for child in children:
        if sha256(child.content.encode()).hexdigest() != child.content_hash:
            raise EvidenceContractError("CHILD_CONTENT_HASH_INVALID")
        parent = by_id.get(child.parent_id)
        if parent is None or any(
            getattr(child, field) != getattr(parent, field)
            for field in (
                "knowledge_base_id",
                "document_id",
                "document_version_id",
                "index_release_id",
                "section_path",
            )
        ):
            raise EvidenceContractError("PARENT_EVIDENCE_MISMATCH")
        if sha256(parent.content.encode()).hexdigest() != parent.content_hash:
            raise EvidenceContractError("PARENT_CONTENT_HASH_INVALID")
        if (
            child.hit_start_offset is not None or child.hit_end_offset is not None
        ) and (
            child.hit_start_offset is None
            or child.hit_end_offset is None
            or child.hit_start_offset < 0
            or child.hit_end_offset <= child.hit_start_offset
            or child.hit_end_offset > len(parent.content)
            or parent.content[child.hit_start_offset : child.hit_end_offset]
            != child.content
        ):
            raise EvidenceContractError("PARENT_CHILD_OFFSET_INVALID")


async def verify_equivalence(
    children: tuple[Evidence, ...],
    parents: tuple[ParentEvidence, ...],
    vectors: dict[UUID, tuple[float, ...]],
    *,
    question: str,
    threshold: float,
    pair_limit: int,
    gateway: StructuredStageGateway,
    stage_bound: bool,
) -> tuple[tuple[Evidence, ...], tuple[EquivalenceDecision, ...]]:
    by_id = {p.parent_id: p for p in parents}
    pairs: dict[frozenset[UUID], tuple[float, Evidence, Evidence]] = {}
    for left, right in combinations(children, 2):
        if left.parent_id == right.parent_id or any(
            getattr(left, key) != getattr(right, key)
            for key in (
                "knowledge_base_id",
                "document_id",
                "document_version_id",
                "section_path",
            )
        ):
            continue
        a, b = vectors.get(left.chunk_id), vectors.get(right.chunk_id)
        if not a or not b or len(a) != len(b) or not all(isfinite(x) for x in (*a, *b)):
            raise StructuredModelError(
                "STORED_CHUNK_VECTOR_INVALID", "已存子片段向量无效"
            )
        norm = sqrt(sum(x * x for x in a)) * sqrt(sum(x * x for x in b))
        if not norm:
            raise StructuredModelError(
                "STORED_CHUNK_VECTOR_INVALID", "已存子片段向量无效"
            )
        similarity = sum(x * y for x, y in zip(a, b, strict=True)) / norm
        key = frozenset((left.parent_id, right.parent_id))
        if similarity >= threshold and (key not in pairs or similarity > pairs[key][0]):
            pairs[key] = (similarity, left, right)
    decisions = []
    accepted: set[frozenset[UUID]] = set()
    selected_pairs = sorted(
        pairs.values(), key=lambda p: (-p[0], str(p[1].chunk_id), str(p[2].chunk_id))
    )[:pair_limit]

    async def check_pair(left: Evidence, right: Evidence):
        return await gateway.complete(
            "equivalence",
            {
                "question": question,
                "left": _input(left, by_id[left.parent_id]),
                "right": _input(right, by_id[right.parent_id]),
            },
            EquivalenceResult,
        )

    results = (
        await asyncio.gather(
            *(check_pair(left, right) for _, left, right in selected_pairs),
            return_exceptions=True,
        )
        if stage_bound
        else (None,) * len(selected_pairs)
    )
    for (similarity, left, right), outcome in zip(selected_pairs, results, strict=True):
        result = None
        reason = "PROMPT_STAGE_NOT_BOUND"
        if stage_bound:
            try:
                if isinstance(outcome, BaseException):
                    raise outcome
                result = outcome
                if (
                    result.left_chunk_id != left.chunk_id
                    or result.right_chunk_id != right.chunk_id
                ):
                    reason = "EQUIVALENCE_ID_INVALID"
                elif (
                    not result.left_quote.strip()
                    or not result.right_quote.strip()
                    or (
                        result.left_quote not in by_id[left.parent_id].content
                        or result.right_quote not in by_id[right.parent_id].content
                    )
                ):
                    reason = "EQUIVALENCE_QUOTE_INVALID"
                elif result.differing_conditions:
                    reason = "DIFFERING_CONDITIONS"
                elif result.verdict == "EQUIVALENT":
                    reason = "VERIFIED_EQUIVALENT"
                    accepted.add(frozenset((left.parent_id, right.parent_id)))
                else:
                    reason = result.verdict
            except StructuredModelError as error:
                reason = error.code
            except ValidationError:
                reason = "EQUIVALENCE_CONTRACT_INVALID"
            # 可选等价阶段失败时保留原证据，只冻结错误类型，不输出异常正文。
            except Exception as error:  # noqa: BLE001
                reason = getattr(error, "code", type(error).__name__)
        decisions.append(
            EquivalenceDecision(
                left=left,
                right=right,
                left_parent=by_id[left.parent_id],
                right_parent=by_id[right.parent_id],
                similarity=similarity,
                reason=reason,
                result=result,
            )
        )
    # 完全连接分组：不能通过 A=B、B=C 推断未经核验的 A=C。
    groups: list[list[UUID]] = []
    parent_order = tuple(
        dict.fromkeys(c.parent_id for c in sorted(children, key=lambda c: -c.score))
    )
    removed: dict[UUID, UUID] = {}
    for parent_id in parent_order:
        for group in groups:
            if all(frozenset((parent_id, member)) in accepted for member in group):
                removed[parent_id] = group[0]
                group.append(parent_id)
                break
        else:
            groups.append([parent_id])
    facts = []
    for decision in decisions:
        merged = tuple(
            c.chunk_id
            for c in children
            if c.parent_id in (decision.left.parent_id, decision.right.parent_id)
            and c.parent_id in removed
            and removed[c.parent_id]
            in (decision.left.parent_id, decision.right.parent_id)
        )
        retained = next(
            (removed[c.parent_id] for c in children if c.chunk_id in merged), None
        )
        facts.append(
            decision.model_copy(
                update={"merged_chunk_ids": merged, "retained_parent_id": retained}
            )
        )
    return tuple(c for c in children if c.parent_id not in removed), tuple(facts)


def _input(child: Evidence, parent: ParentEvidence) -> dict[str, object]:
    return {
        "chunk_id": str(child.chunk_id),
        "parent_id": str(parent.parent_id),
        "content": parent.content,
        "section_path": parent.section_path,
        "page_start": parent.page_no,
        "page_end": parent.page_end,
        "content_hash": parent.content_hash,
    }
