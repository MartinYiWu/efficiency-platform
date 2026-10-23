"""把重排子命中组装为预算内的完整父证据。"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from .state import Evidence, EvidenceGroup, ParentEvidence


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
