"""从结构化模型流中只释放完整且引用有效的公司回答段落。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from uuid import UUID

from .citations import CitationGuardError
from .state import CompanyParagraph, EvidencePack

_SECTIONS = re.compile(r'"company_sections"\s*:\s*\[')
_TITLE = re.compile(r'"title"\s*:\s*("(?:\\.|[^"\\])*")')


class AnswerSectionStream:
    def __init__(self, evidence: EvidencePack, emit: Callable[[str], None]) -> None:
        self.allowed = {entry.chunk_id for entry in evidence.entries}
        self.emit = emit
        self.emitted_paragraphs = 0
        self.citation_numbers: dict[UUID, int] = {}
        self.last_header_section_start = -1
        self.disabled = False

    def feed(self, content: str) -> None:
        if self.disabled:
            return
        match = _SECTIONS.search(content)
        if match is None:
            return
        depth = 0
        section_start = -1
        paragraph_start = -1
        quoted = False
        escaped = False
        completed = 0
        for index in range(match.end(), len(content)):
            char = content[index]
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
                continue
            if char == '"':
                quoted = True
            elif char == "{":
                depth += 1
                if depth == 1:
                    section_start = index
                elif depth == 2:
                    paragraph_start = index
            elif char == "}":
                if depth == 2 and paragraph_start >= 0:
                    completed += 1
                    if completed > self.emitted_paragraphs:
                        title_match = _TITLE.search(
                            content, section_start, paragraph_start
                        )
                        if title_match is None:
                            self.disabled = True
                            return
                        title = json.loads(title_match.group(1))
                        paragraph = CompanyParagraph.model_validate_json(
                            content[paragraph_start : index + 1]
                        )
                        if not set(paragraph.supporting_chunk_ids).issubset(
                            self.allowed
                        ):
                            raise CitationGuardError("流式段落包含证据之外的引用")
                        if section_start != self.last_header_section_start:
                            self.emit(f"## {title}")
                            self.last_header_section_start = section_start
                        suffix = ""
                        for chunk_id in paragraph.supporting_chunk_ids:
                            if chunk_id not in self.citation_numbers:
                                self.citation_numbers[chunk_id] = (
                                    len(self.citation_numbers) + 1
                                )
                            suffix += f"[{self.citation_numbers[chunk_id]}]"
                        self.emit(f"{paragraph.text}{suffix}")
                        self.emitted_paragraphs = completed
                    paragraph_start = -1
                depth -= 1
                if depth < 0:
                    return


__all__ = ["AnswerSectionStream"]
