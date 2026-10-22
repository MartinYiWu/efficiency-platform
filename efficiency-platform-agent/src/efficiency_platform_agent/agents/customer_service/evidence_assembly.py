"""把重排子命中组装为预算内的完整父证据。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .state import Evidence, ParentEvidence


@dataclass(frozen=True, slots=True)
class EvidenceAssembly:
    selected: tuple[Evidence, ...]
    selected_parents: tuple[ParentEvidence, ...]
    hit_chunk_ids: dict[UUID, tuple[UUID, ...]]
    excluded_parent_ids: tuple[UUID, ...]
    duplicate_parent_ids: tuple[UUID, ...]
    context_token_limit: int
    used_tokens: int


def assemble_evidence(
    children: tuple[Evidence, ...],
    parents: tuple[ParentEvidence, ...],
    *,
    context_token_limit: int,
    reserved_tokens: int,
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
        if used_tokens + parent.token_count > context_token_limit:
            excluded.append(parent.parent_id)
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
    return EvidenceAssembly(
        selected=tuple(selected),
        selected_parents=tuple(selected_parents),
        hit_chunk_ids={key: tuple(value) for key, value in hits.items()},
        excluded_parent_ids=tuple(excluded),
        duplicate_parent_ids=tuple(duplicates),
        context_token_limit=context_token_limit,
        used_tokens=used_tokens,
    )
