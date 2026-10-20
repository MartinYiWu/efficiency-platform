"""回答引用闭包与冻结引用生成。"""

from __future__ import annotations

from .state import AnswerMode, Citation, CustomerServiceAnswer, Evidence


class CitationGuardError(ValueError):
    code = "CITATION_CLOSURE_INVALID"


def validate_citation_closure(
    answer: CustomerServiceAnswer, evidence: tuple[Evidence, ...]
) -> None:
    allowed = {item.chunk_id for item in evidence}
    referenced = {
        chunk_id
        for section in answer.company_sections
        for paragraph in section.paragraphs
        for chunk_id in paragraph.supporting_chunk_ids
    }
    if not referenced.issubset(allowed):
        raise CitationGuardError("回答包含候选证据之外的引用")
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
    answer: CustomerServiceAnswer, evidence: tuple[Evidence, ...]
) -> tuple[Citation, ...]:
    by_id = {item.chunk_id: item for item in evidence}
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
        )
        for index, item in enumerate(ordered, 1)
    )


__all__ = ["CitationGuardError", "freeze_citations", "validate_citation_closure"]
