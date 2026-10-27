"""回答引用闭包与冻结引用生成。"""

from __future__ import annotations

from hashlib import sha256

from .state import (
    AnswerMode,
    Citation,
    CustomerServiceAnswer,
    Evidence,
    EvidencePack,
    EvidencePackEntry,
)


class CitationGuardError(ValueError):
    code = "CITATION_CLOSURE_INVALID"


def validate_citation_closure(
    answer: CustomerServiceAnswer, evidence: tuple[Evidence, ...] | EvidencePack
) -> None:
    entries: tuple[Evidence, ...]
    if isinstance(evidence, EvidencePack):
        pack = evidence
        validate_evidence_pack(pack)
        if pack.blocked and answer.company_sections:
            raise CitationGuardError("冻结证据包禁止公司事实回答")
        entries = pack.entries
    else:
        pack = None
        entries = evidence
    allowed = {item.chunk_id for item in entries}
    referenced = {
        chunk_id
        for section in answer.company_sections
        for paragraph in section.paragraphs
        for chunk_id in paragraph.supporting_chunk_ids
    }
    if not referenced.issubset(allowed):
        raise CitationGuardError("回答包含候选证据之外的引用")
    for item in entries:
        if pack is not None:
            continue
        if item.parent_id is None:
            continue
        if (
            item.hit_content is None
            or item.hit_content_hash is None
            or item.hit_start_offset is None
            or item.hit_end_offset is None
            or item.content[item.hit_start_offset : item.hit_end_offset]
            != item.hit_content
            or sha256(item.hit_content.encode("utf-8")).hexdigest()
            != item.hit_content_hash
        ):
            raise CitationGuardError("引用子片段不能定位到完整父原文")
    if (
        answer.answer_mode in {AnswerMode.COMPANY_KNOWLEDGE, AnswerMode.MIXED}
        and not referenced
    ):
        raise CitationGuardError("公司事实必须具有引用")
    if (
        answer.answer_mode not in {AnswerMode.COMPANY_KNOWLEDGE, AnswerMode.MIXED}
        and referenced
    ):
        raise CitationGuardError("非公司回答不得携带引用")


def freeze_citations(
    answer: CustomerServiceAnswer, evidence: tuple[Evidence, ...] | EvidencePack
) -> tuple[Citation, ...]:
    entries: tuple[Evidence, ...]
    if isinstance(evidence, EvidencePack):
        pack = evidence
        validate_citation_closure(answer, pack)
        entries = pack.entries
    else:
        pack = None
        entries = evidence
    by_id = {item.chunk_id: item for item in entries}
    ordered: list[Evidence] = []
    seen = set()
    for section in answer.company_sections:
        for paragraph in section.paragraphs:
            for chunk_id in paragraph.supporting_chunk_ids:
                if chunk_id not in seen:
                    ordered.append(by_id[chunk_id])
                    seen.add(chunk_id)
    return tuple(
        Citation(
            citation_no=index,
            knowledge_base_id=item.knowledge_base_id,
            document_id=item.document_id,
            document_version_id=item.document_version_id,
            index_release_id=item.index_release_id,
            chunk_id=item.chunk_id,
            document_title=item.document_title,
            version_no=item.version_no,
            section_path=item.section_path,
            page_no=item.page_no,
            quoted_text=item.content,
            content_hash=item.content_hash,
            parent_id=item.parent_id if pack is not None else None,
            citation_type=item.citation_type
            if pack is not None and isinstance(item, EvidencePackEntry)
            else "FULL_PARENT",
            original_spans=item.original_spans
            if pack is not None and isinstance(item, EvidencePackEntry)
            else (),
        )
        for index, item in enumerate(ordered, 1)
    )


def validate_evidence_pack(pack: EvidencePack) -> None:
    from .evidence_extract import split_sentences

    for item in pack.entries:
        parent = item.original_parent
        if (
            item.hit_start_offset is None
            or item.hit_end_offset is None
            or not 0
            <= item.hit_start_offset
            < item.hit_end_offset
            <= len(parent.content)
            or item.hit_content is None
            or parent.content[item.hit_start_offset : item.hit_end_offset]
            != item.hit_content
            or sha256(item.hit_content.encode()).hexdigest() != item.hit_content_hash
        ):
            raise CitationGuardError("冻结子命中无法定位到父原文")
        if (
            sha256(parent.content.encode()).hexdigest() != parent.content_hash
            or any(
                getattr(item, key) != getattr(parent, key)
                for key in (
                    "parent_id",
                    "knowledge_base_id",
                    "document_id",
                    "document_version_id",
                    "index_release_id",
                    "content_hash",
                )
            )
            or item.chunk_id not in item.hit_chunk_ids
        ):
            raise CitationGuardError("冻结证据原文或版本不一致")
        pieces = []
        end = 0
        for span in item.original_spans:
            if not end <= span.start_offset < span.end_offset <= len(parent.content):
                raise CitationGuardError("原文偏移无效")
            piece = parent.content[span.start_offset : span.end_offset]
            if sha256(piece.encode()).hexdigest() != span.content_hash:
                raise CitationGuardError("原文节选哈希无效")
            pieces.append(piece)
            end = span.end_offset
        if item.citation_type == "FULL_PARENT":
            if (
                len(item.original_spans) != 1
                or item.original_spans[0].start_offset != 0
                or end != len(parent.content)
                or item.content != parent.content
            ):
                raise CitationGuardError("完整父引用不得截断")
        else:
            if (
                parent.evidence_mode != "EXTRACTIVE_NARRATIVE"
                or parent.block_kind != "PARAGRAPH"
                or item.content != "\n".join(pieces)
            ):
                raise CitationGuardError("不允许节选或节选内容无效")
            try:
                boundaries = {
                    (s.start_offset, s.end_offset)
                    for s in split_sentences(parent.content)
                }
            except ValueError as error:
                raise CitationGuardError("无法可靠定位原句") from error
            if any(
                (s.start_offset, s.end_offset) not in boundaries
                for s in item.original_spans
            ):
                raise CitationGuardError("引用必须为完整原句")


__all__ = ["CitationGuardError", "freeze_citations", "validate_citation_closure"]
