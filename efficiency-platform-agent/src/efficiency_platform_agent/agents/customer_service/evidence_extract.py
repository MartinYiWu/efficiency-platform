"""只选择可逐字校验的原文完整句段，禁止模型摘要。"""

import re
from hashlib import sha256
from uuid import UUID

from .state import EvidenceSpan, ExtractionSelection, StrictModel


class SourceSentence(StrictModel):
    sentence_id: int
    text: str
    start_offset: int
    end_offset: int


def split_sentences(text: str) -> tuple[SourceSentence, ...]:
    sentences = []
    # 无法可靠区分英文缩写、句点或残句时，整段拒绝抽取。
    for paragraph in re.finditer(r"[^\r\n]+", text):
        offset = paragraph.start()
        for match in re.finditer(r"[^。！？!?]+[。！？!?]+[”’\"']?", paragraph.group()):
            if paragraph.group()[offset - paragraph.start() : match.start()].strip():
                raise ValueError("EXTRACTION_SENTENCE_BOUNDARY_INVALID")
            start = paragraph.start() + match.start()
            end = paragraph.start() + match.end()
            sentences.append(
                SourceSentence(
                    sentence_id=len(sentences) + 1,
                    text=text[start:end],
                    start_offset=start,
                    end_offset=end,
                )
            )
            offset = end
        if text[offset : paragraph.end()].strip():
            raise ValueError("EXTRACTION_SENTENCE_BOUNDARY_INVALID")
    if not sentences:
        raise ValueError("EXTRACTION_SENTENCE_BOUNDARY_INVALID")
    return tuple(sentences)


def select_spans(
    text: str,
    parent_id: UUID,
    sentences: tuple[SourceSentence, ...],
    selection: ExtractionSelection,
) -> tuple[EvidenceSpan, ...]:
    ids = selection.selected_sentence_ids
    if (
        selection.parent_id != parent_id
        or not ids
        or len(set(ids)) != len(ids)
        or not set(ids) <= {s.sentence_id for s in sentences}
    ):
        raise ValueError("EXTRACTION_SELECTION_INVALID")
    if sentences != split_sentences(text):
        raise ValueError("EXTRACTION_OFFSET_INVALID")
    return tuple(
        EvidenceSpan(
            start_offset=s.start_offset,
            end_offset=s.end_offset,
            content_hash=sha256(s.text.encode()).hexdigest(),
        )
        for s in sentences
        if s.sentence_id in ids
    )
