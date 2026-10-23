"""把重排子命中组装为预算内的完整父证据。"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from uuid import UUID

from .conflict_screen import ConflictScreen
from .evidence_extract import ExtractionSelection, select_spans, split_sentences
from .intent import StructuredStageGateway
from .model_gateway import ReleaseStructuredModelGateway
from .release_bundle import CustomerServiceReleaseBundle
from .state import (
    CustomerServiceAnswer,
    Evidence,
    EvidenceBudget,
    EvidenceExclusion,
    EvidenceGroup,
    EvidencePack,
    EvidencePackEntry,
    EvidenceSpan,
    HistoryMessage,
    IntentDecision,
    ParentEvidence,
    SufficiencyDecision,
)


@dataclass(frozen=True, slots=True)
class EvidenceAssembly:
    selected: tuple[Evidence, ...]
    selected_parents: tuple[ParentEvidence, ...]
    hit_chunk_ids: dict[UUID, tuple[UUID, ...]]
    excluded_parent_ids: tuple[UUID, ...]
    duplicate_parent_ids: tuple[UUID, ...]
    context_token_limit: int
    used_tokens: int
    candidate_parents: tuple[ParentEvidence, ...] = ()
    groups: tuple[EvidenceGroup, ...] = ()
    exclusion_reasons: dict[UUID, str] = field(default_factory=dict)
    grouping_reasons: dict[UUID, str] = field(default_factory=dict)


def assemble_evidence(
    children: tuple[Evidence, ...],
    parents: tuple[ParentEvidence, ...],
    *,
    context_token_limit: int,
    reserved_tokens: int,
    final_evidence_top_k: int | None = None,
    adjacent_group_max_parents: int = 1,
) -> EvidenceAssembly:
    if context_token_limit <= 0 or reserved_tokens < 0:
        raise ValueError("CONTEXT_BUDGET_INVALID")
    parent_by_id = {parent.parent_id: parent for parent in parents}
    hits: dict[UUID, list[UUID]] = {}
    selected: list[Evidence] = []
    selected_parents: list[ParentEvidence] = []
    excluded: list[UUID] = []
    duplicates: list[UUID] = []
    seen: set[UUID] = set()
    seen_content: set[tuple[UUID, str, str]] = set()
    used_tokens = reserved_tokens
    candidates: list[ParentEvidence] = []
    reasons: dict[UUID, str] = {}
    for child in children:
        if child.parent_id is None:
            raise ValueError("PARENT_EVIDENCE_MISSING")
        parent = parent_by_id.get(child.parent_id)
        if parent is None or (
            child.document_version_id != parent.document_version_id
            or child.index_release_id != parent.index_release_id
            or child.knowledge_base_id != parent.knowledge_base_id
        ):
            raise ValueError("PARENT_EVIDENCE_MISMATCH")
        hits.setdefault(child.parent_id, []).append(child.chunk_id)
        if child.parent_id in seen:
            continue
        seen.add(child.parent_id)
        content_key = (
            parent.document_version_id,
            parent.content_hash,
            parent.content,
        )
        if content_key in seen_content:
            duplicates.append(parent.parent_id)
            continue
        seen_content.add(content_key)
        if final_evidence_top_k is not None and len(candidates) >= final_evidence_top_k:
            reasons[parent.parent_id] = "FINAL_TOP_K_EXCLUDED"
            continue
        candidates.append(parent)
        if used_tokens + parent.token_count > context_token_limit:
            excluded.append(parent.parent_id)
            if final_evidence_top_k is not None:
                reasons[parent.parent_id] = "BUDGET_EXCLUDED"
            continue
        selected.append(
            child.model_copy(
                update={
                    "hit_content": child.content,
                    "hit_content_hash": child.content_hash,
                    "hit_start_offset": child.hit_start_offset,
                    "hit_end_offset": child.hit_end_offset,
                    "content": parent.content,
                    "content_hash": parent.content_hash,
                    "section_path": parent.section_path,
                }
            )
        )
        selected_parents.append(parent)
        used_tokens += parent.token_count
    groups: list[EvidenceGroup] = []
    grouping_reasons = {
        p.parent_id: "TABLE_IDENTITY_UNAVAILABLE"
        for p in candidates
        if p.block_kind == "TABLE" and p.source_table_id is None
    }
    ordered = sorted(
        candidates, key=lambda p: (str(p.document_version_id), p.parent_no or 0)
    )
    run: list[ParentEvidence] = []
    for parent in ordered:
        previous = run[-1] if run else None
        adjacent = previous is not None and (
            parent.document_version_id == previous.document_version_id
            and parent.document_id == previous.document_id
            and parent.index_release_id == previous.index_release_id
            and parent.knowledge_base_id == previous.knowledge_base_id
            and parent.parent_no is not None
            and previous.parent_no is not None
            and parent.parent_no == previous.parent_no + 1
            and parent.section_path == previous.section_path
            and (
                parent.block_kind == previous.block_kind == "PARAGRAPH"
                or (
                    parent.block_kind == previous.block_kind == "TABLE"
                    and parent.source_table_id is not None
                    and parent.source_table_id == previous.source_table_id
                )
            )
            and len(run) < adjacent_group_max_parents
        )
        if not adjacent:
            if len(run) > 1:
                groups.append(EvidenceGroup(parent_ids=tuple(p.parent_id for p in run)))
            run = []
        run.append(parent)
    if len(run) > 1:
        groups.append(EvidenceGroup(parent_ids=tuple(p.parent_id for p in run)))
    if groups:
        by_id = {x.parent_id: x for x in selected}
        grouped = {
            pid: group.parent_ids for group in groups for pid in group.parent_ids
        }
        arranged = []
        for item in selected:
            for pid in grouped.get(item.parent_id, (item.parent_id,)):
                if pid in by_id:
                    arranged.append(by_id.pop(pid))
        selected = arranged
        selected_parents = [parent_by_id[x.parent_id] for x in selected]
    return EvidenceAssembly(
        selected=tuple(selected),
        selected_parents=tuple(selected_parents),
        hit_chunk_ids={key: tuple(value) for key, value in hits.items()},
        excluded_parent_ids=tuple(excluded),
        duplicate_parent_ids=tuple(duplicates),
        context_token_limit=context_token_limit,
        used_tokens=used_tokens,
        candidate_parents=tuple(candidates),
        groups=tuple(groups),
        exclusion_reasons=reasons,
        grouping_reasons=grouping_reasons,
    )


async def build_evidence_pack(
    assembly: EvidenceAssembly,
    *,
    bundle: CustomerServiceReleaseBundle,
    gateway: StructuredStageGateway,
    question: str,
    history: tuple[HistoryMessage, ...],
    conflict_screen: ConflictScreen | None,
    children: tuple[Evidence, ...] | None = None,
    intent: IntentDecision | None = None,
) -> EvidencePack:
    """从最终候选一次冻结证据；后续阶段不能重新挑选原文。"""
    if not bundle.contract_version.endswith("/2"):
        raise ValueError("EVIDENCE_PACK_REQUIRES_RELEASE_V2")
    renderer = ReleaseStructuredModelGateway(None, bundle)
    policy = bundle.model_policy
    candidates = assembly.candidate_parents
    by_parent = {}
    for child in children if children is not None else assembly.selected:
        if child.chunk_id in assembly.hit_chunk_ids.get(child.parent_id, ()):
            by_parent.setdefault(child.parent_id, child)
    entries = []
    for parent in candidates:
        child = by_parent[parent.parent_id]
        if sha256(parent.content.encode()).hexdigest() != parent.content_hash or any(
            getattr(child, key) != getattr(parent, key)
            for key in (
                "knowledge_base_id",
                "document_id",
                "document_version_id",
                "index_release_id",
            )
        ):
            raise ValueError("EVIDENCE_SOURCE_INVALID")
        entries.append(
            EvidencePackEntry(
                **child.model_copy(
                    update={
                        "content": parent.content,
                        "content_hash": parent.content_hash,
                        "section_path": parent.section_path,
                        "hit_content": child.hit_content
                        if child.hit_content is not None
                        else child.content,
                        "hit_content_hash": child.hit_content_hash
                        if child.hit_content_hash is not None
                        else child.content_hash,
                    }
                ).model_dump(),
                original_parent=parent,
                citation_type="FULL_PARENT",
                original_spans=(
                    EvidenceSpan(
                        start_offset=0,
                        end_offset=len(parent.content),
                        content_hash=parent.content_hash,
                    ),
                ),
                hit_chunk_ids=assembly.hit_chunk_ids[parent.parent_id],
            )
        )

    def input_cost(selected):
        value = {
            "question": question,
            "history": [h.model_dump(mode="json") for h in history],
            "evidence": [e.model_input() for e in selected],
        }
        answer_value = value | {
            "intent": intent.model_dump(mode="json") if intent else None,
            "sufficiency": None,
        }
        return max(
            renderer.input_tokens("sufficiency", value, SufficiencyDecision),
            *(
                renderer.input_tokens(stage, answer_value, CustomerServiceAnswer)
                for stage in ("answer_company", "answer_mixed")
            ),
            renderer.input_tokens(
                "answer_repair",
                {"original_input": answer_value, "validation_error": "验证失败"},
                CustomerServiceAnswer,
            ),
        )

    def budget_for(model):
        limit = min(bundle.rag_policy.context_token_limit, model.max_input_tokens)
        safety = max(256, limit // 10)
        # 充分性输出和意图进入回答输入；额外预留一份输出及结构字段空间。
        copies = max(
            sum(
                message.content_template.count("{{input_json}}")
                for message in renderer._stage_messages(stage)
            )
            for stage in ("answer_company", "answer_mixed", "answer_repair")
        )
        reserve = input_cost(()) + (1 + copies) * model.max_output_tokens + safety + 512
        return limit, safety, reserve

    limit, safety, reserved = budget_for(policy)
    empty_cost = input_cost(())

    def cost(selected):
        return input_cost(selected) - empty_cost

    protected = [
        entry
        for entry in entries
        if entry.original_parent.evidence_mode != "EXTRACTIVE_NARRATIVE"
        or entry.original_parent.block_kind != "PARAGRAPH"
    ]
    oversized = any(reserved + cost((entry,)) > limit for entry in protected)
    alternative = bundle.large_context_model_policy
    if (
        oversized
        and alternative is not None
        and alternative.max_input_tokens > policy.max_input_tokens
    ):
        policy = alternative
        limit, safety, reserved = budget_for(policy)
    blocked = bool(conflict_screen and conflict_screen.blocked)
    reasons = ["CONFLICT_SCREEN_BLOCKED"] if blocked else []
    exclusions = [
        EvidenceExclusion(parent_id=pid, reason=reason)
        for pid, reason in assembly.exclusion_reasons.items()
        if reason != "BUDGET_EXCLUDED"
    ]
    selected = []
    extraction_decisions = []
    # 争议双方作为原子集合，预算无法容纳时整组排除，快照仍保留前置冲突事实。
    if blocked:
        if reserved + cost(entries) <= limit:
            selected = entries
        else:
            exclusions.extend(
                EvidenceExclusion(
                    parent_id=e.parent_id, reason="CONFLICT_BUDGET_EXCLUDED"
                )
                for e in entries
            )
            reasons.append("CONFLICT_BUDGET_EXCEEDED")
    else:
        for entry in entries:
            if reserved + cost((*selected, entry)) <= limit:
                selected.append(entry)
                continue
            parent = entry.original_parent
            reason = "BUDGET_EXCLUDED"
            if entry in protected:
                if reserved + cost((entry,)) > limit:
                    blocked = True
                    reasons.append("PROTECTED_PARENT_TOO_LARGE")
            else:
                try:
                    sentences = split_sentences(parent.content)
                    available = max(0, limit - reserved - cost(selected))
                    value = {
                        "question": question,
                        "parent_id": str(parent.parent_id),
                        "sentences": [s.model_dump(mode="json") for s in sentences],
                        "available_tokens": available,
                    }
                    extraction_policy = bundle.model_policy
                    extraction_cost = renderer.input_tokens(
                        "evidence_extract", value, ExtractionSelection
                    )
                    if (
                        extraction_cost
                        + extraction_policy.max_output_tokens
                        + max(256, extraction_policy.max_input_tokens // 10)
                        > extraction_policy.max_input_tokens
                    ):
                        raise ValueError("EXTRACTION_INPUT_TOO_LARGE")
                    response = await gateway.complete(
                        "evidence_extract", value, ExtractionSelection
                    )
                    response = ExtractionSelection.model_validate(response.model_dump())
                    extraction_decisions.append(response)
                    spans = select_spans(
                        parent.content, parent.parent_id, sentences, response
                    )
                    extracted = entry.model_copy(
                        update={
                            "content": "\n".join(
                                parent.content[s.start_offset : s.end_offset]
                                for s in spans
                            ),
                            "citation_type": "EXTRACTED_SPANS",
                            "original_spans": spans,
                        }
                    )
                    if reserved + cost((*selected, extracted)) > limit:
                        raise ValueError("EXTRACTION_RESULT_TOO_LARGE")
                    selected.append(extracted)
                    continue
                except Exception as error:  # noqa: BLE001
                    known = {
                        "EXTRACTION_SENTENCE_BOUNDARY_INVALID",
                        "EXTRACTION_SELECTION_INVALID",
                        "EXTRACTION_OFFSET_INVALID",
                        "EXTRACTION_INPUT_TOO_LARGE",
                        "EXTRACTION_RESULT_TOO_LARGE",
                    }
                    reason = getattr(
                        error,
                        "code",
                        str(error) if str(error) in known else "EXTRACTION_FAILED",
                    )
            exclusions.append(
                EvidenceExclusion(parent_id=parent.parent_id, reason=reason)
            )
    selected_ids = {e.parent_id for e in selected}
    groups = tuple(
        EvidenceGroup(
            parent_ids=tuple(pid for pid in g.parent_ids if pid in selected_ids)
        )
        for g in assembly.groups
        if sum(pid in selected_ids for pid in g.parent_ids) > 1
    )
    by_id = {entry.parent_id: entry for entry in selected}
    grouped = {pid: group.parent_ids for group in groups for pid in group.parent_ids}
    arranged = []
    for entry in selected:
        for pid in grouped.get(entry.parent_id, (entry.parent_id,)):
            if pid in by_id:
                arranged.append(by_id.pop(pid))
    selected = arranged
    return EvidencePack(
        entries=tuple(selected),
        groups=groups,
        exclusions=tuple(exclusions),
        model_policy=policy,
        budget=EvidenceBudget(
            context_token_limit=limit,
            reserved_tokens=reserved,
            used_tokens=reserved + cost(selected),
            output_tokens=policy.max_output_tokens,
            safety_tokens=safety,
            fixed_input_tokens=empty_cost,
            intermediate_output_tokens=reserved
            - empty_cost
            - policy.max_output_tokens
            - safety,
            evidence_tokens=cost(selected),
        ),
        blocked=blocked,
        block_reasons=tuple(dict.fromkeys(reasons)),
        extraction_decisions=tuple(extraction_decisions),
        conflict_screen=conflict_screen,
    )
