"""验证完成后再生成公开答案与 SSE 片段。"""

from __future__ import annotations

from .citations import freeze_citations
from .state import AnswerMode, CustomerServiceAnswer, Evidence, RenderedAnswer


def render_answer(answer: CustomerServiceAnswer, evidence: tuple[Evidence, ...]) -> RenderedAnswer:
    citations = freeze_citations(answer, evidence)
    citation_by_chunk = {item.chunk_id: item.citation_no for item in citations}
    blocks: list[str] = []
    for section in answer.company_sections:
        blocks.append(f"## {section.title}")
        for paragraph in section.paragraphs:
            suffix = "".join(f"[{citation_by_chunk[item]}]" for item in paragraph.supporting_chunk_ids)
            blocks.append(f"{paragraph.text}{suffix}")
    if answer.general_advice is not None:
        blocks.append(f"## {answer.general_advice.title}")
        blocks.extend(answer.general_advice.paragraphs)
    if answer.answer_mode is AnswerMode.CLARIFY:
        blocks.append(answer.clarification_question or "")
    if answer.answer_mode is AnswerMode.INSUFFICIENT_EVIDENCE:
        blocks.append(answer.insufficiency_reason or "")
    return RenderedAnswer(answer=answer, markdown="\n\n".join(filter(None, blocks)), citations=citations)


def answer_deltas(rendered: RenderedAnswer) -> tuple[str, ...]:
    return tuple(part for part in rendered.markdown.split("\n\n") if part)


__all__ = ["answer_deltas", "render_answer"]
