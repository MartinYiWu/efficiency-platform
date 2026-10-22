"""按标题、段落、列表和表格边界执行确定性分块。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from .contracts import BlockKind, ChunkDraft, EvidenceMode, ParentDraft, ParsedDocument

_TOKEN = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u9fff]|[^\s]", re.UNICODE)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}")
_NUMBERED_CLAUSE = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百千0-9]+条|[0-9]+[.、])\s*"
)


@dataclass(frozen=True, slots=True)
class _Block:
    text: str
    section_path: str | None
    page_no: int | None = None
    page_end: int | None = None
    source_start: int | None = None
    source_offsets: tuple[tuple[int, int], ...] = ()


def count_tokens(text: str) -> int:
    return len(_TOKEN.findall(text))


def chunk_document(
    document: ParsedDocument,
    *,
    max_tokens: int = 800,
    overlap_tokens: int = 120,
) -> tuple[ChunkDraft, ...]:
    if max_tokens < 8 or overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("CHUNK_LIMIT_INVALID")
    blocks = _document_blocks(document.markdown)
    pieces: list[_Block] = []
    for block in blocks:
        if _is_table(block.text):
            pieces.extend(_split_table(block, max_tokens))
        else:
            pieces.extend(_split_text_block(block, max_tokens, overlap_tokens))
    unique: list[_Block] = []
    seen: set[str] = set()
    for piece in pieces:
        content = piece.text.strip()
        digest = sha256(content.encode("utf-8")).hexdigest()
        if not content or digest in seen or _is_navigation_noise(content):
            continue
        seen.add(digest)
        unique.append(_Block(content, piece.section_path, piece.page_no))
    if not unique:
        raise ValueError("DOCUMENT_HAS_NO_CHUNKS")
    return tuple(
        ChunkDraft(
            chunk_no=index,
            section_path=block.section_path,
            page_no=block.page_no,
            content=block.text,
            content_hash=sha256(block.text.encode("utf-8")).hexdigest(),
            token_count=count_tokens(block.text),
        )
        for index, block in enumerate(unique, 1)
    )


def parent_child_document(
    document: ParsedDocument,
    *,
    parent_max_tokens: int = 2400,
    child_max_tokens: int = 400,
    child_overlap_tokens: int = 40,
    evidence_mode: EvidenceMode = "FULL_ONLY",
) -> tuple[ParentDraft, ...]:
    if (
        parent_max_tokens < child_max_tokens
        or child_max_tokens < 8
        or child_overlap_tokens < 0
        or child_overlap_tokens >= child_max_tokens
    ):
        raise ValueError("CHUNK_LIMIT_INVALID")
    parents: list[ParentDraft] = []
    next_chunk_no = 1
    for block in _expand_parent_blocks(
        _parent_blocks(document.markdown, document.page_markers),
        parent_max_tokens,
        document.page_markers,
    ):
        if _is_navigation_noise(block.text):
            continue
        token_count = count_tokens(block.text)
        if token_count > parent_max_tokens:
            raise ValueError("PARENT_CLAUSE_TOO_LONG")
        parts = _split_text_block(block, child_max_tokens, child_overlap_tokens)
        parent_no = len(parents) + 1
        children: list[ChunkDraft] = []
        search_offset = 0
        for child_no, part in enumerate(parts, 1):
            start_offset = block.text.find(part.text, search_offset)
            if start_offset < 0:
                raise ValueError("PARENT_CHILD_POSITION_INVALID")
            end_offset = start_offset + len(part.text)
            page_no = block.page_no
            source_position = block.source_start
            if block.source_offsets:
                local_start, source_position = block.source_offsets[0]
                for local_offset, absolute_offset in block.source_offsets[1:]:
                    if local_offset > start_offset:
                        break
                    local_start, source_position = local_offset, absolute_offset
                if local_start:
                    source_position += start_offset - local_start
            elif source_position is not None:
                source_position += start_offset
            if source_position is not None:
                for marker_offset, marker_page in document.page_markers:
                    if marker_offset > source_position:
                        break
                    page_no = marker_page
            children.append(
                ChunkDraft(
                    chunk_no=next_chunk_no,
                    parent_no=parent_no,
                    child_no=child_no,
                    section_path=block.section_path,
                    page_no=page_no,
                    content=part.text,
                    content_hash=sha256(part.text.encode("utf-8")).hexdigest(),
                    token_count=count_tokens(part.text),
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
            )
            search_offset = start_offset + 1
            next_chunk_no += 1
        parents.append(
            ParentDraft(
                parent_no=parent_no,
                block_kind=_block_kind(block.text),
                evidence_mode=evidence_mode,
                section_path=block.section_path,
                page_start=block.page_no,
                page_end=block.page_end,
                content=block.text,
                content_hash=sha256(block.text.encode("utf-8")).hexdigest(),
                token_count=token_count,
                children=tuple(children),
            )
        )
    if not parents:
        raise ValueError("DOCUMENT_HAS_NO_CHUNKS")
    return tuple(parents)


def _block_kind(text: str) -> BlockKind:
    if re.search(r"^(?:\s*(?:`{3,}|~{3,})| {4,}\S|\t[ \t]*\S)", text, re.MULTILINE):
        return "CODE"
    if any(_NUMBERED_CLAUSE.match(line) for line in text.splitlines()):
        return "NUMBERED_RULE"
    if re.search(
        r"^\s*(?:[（(][一二三四五六七八九十百千0-9]+[）)]|[一二三四五六七八九十百千]+[、.）]|\d+[）)])",
        text,
        re.MULTILINE,
    ):
        return "NUMBERED_RULE"
    if _is_table(text):
        return "TABLE"
    # 不明确的 Markdown、缩进和混合结构均保持受保护。
    if any(
        re.match(
            r"^(?:\s{2,}|\t|\s*[-+*>|#<`~{\[\\]|\s*[（(]?\d+[)）]|\s*[一二三四五六七八九十]+[、.）])",
            line,
        )
        for line in text.splitlines()
        if line.strip()
    ):
        return "LIST"
    return "PARAGRAPH"


def _expand_parent_blocks(
    blocks: tuple[_Block, ...],
    parent_max_tokens: int,
    page_markers: tuple[tuple[int, int], ...],
) -> tuple[_Block, ...]:
    expanded: list[_Block] = []
    for block in blocks:
        if count_tokens(block.text) <= parent_max_tokens or not _is_table(block.text):
            expanded.append(block)
            continue
        lines = block.text.splitlines()
        header_tokens = count_tokens("\n".join(lines[:2]))
        if header_tokens >= parent_max_tokens or any(
            header_tokens + count_tokens(row) > parent_max_tokens for row in lines[2:]
        ):
            raise ValueError("PARENT_CLAUSE_TOO_LONG")
        source_cursor = len(lines[0]) + len(lines[1]) + 2
        for item in _split_table(block, parent_max_tokens):
            row_positions: list[tuple[int, int, int]] = []
            local_cursor = len(lines[0]) + len(lines[1]) + 2
            for row in item.text.splitlines()[2:]:
                row_start = block.text.find(row, source_cursor)
                if row_start < 0:
                    raise ValueError("PARENT_CHILD_POSITION_INVALID")
                row_positions.append((local_cursor, row_start, len(row)))
                source_cursor = row_start + len(row)
                local_cursor += len(row) + 1
            if not row_positions or block.source_start is None:
                expanded.append(item)
                continue
            first_source = block.source_start + row_positions[0][1]
            last_source = (
                block.source_start + row_positions[-1][1] + row_positions[-1][2] - 1
            )
            page_start = block.page_no
            page_end = block.page_end
            for marker_offset, marker_page in page_markers:
                if marker_offset <= first_source:
                    page_start = marker_page
                if marker_offset <= last_source:
                    page_end = marker_page
                else:
                    break
            expanded.append(
                _Block(
                    item.text,
                    item.section_path,
                    page_start,
                    page_end,
                    None,
                    ((0, first_source),)
                    + tuple(
                        (local_offset, block.source_start + source_offset)
                        for local_offset, source_offset, _ in row_positions
                    ),
                )
            )
    return tuple(expanded)


def _parent_blocks(
    markdown: str, page_markers: tuple[tuple[int, int], ...]
) -> tuple[_Block, ...]:
    headings: list[str] = []
    blocks: list[_Block] = []
    pending: list[str] = []
    numbered = False
    pending_start = 0
    pending_end = 0
    fence: str | None = None

    def page_for(offset: int) -> int | None:
        page = None
        for marker_offset, marker_page in page_markers:
            if marker_offset > offset:
                break
            page = marker_page
        return page

    def flush() -> None:
        nonlocal numbered
        raw = "\n".join(pending)
        content = raw.strip("\n")
        if content.strip():
            content_start = pending_start + raw.find(content)
            blocks.append(
                _Block(
                    content,
                    " / ".join(headings) or None,
                    page_for(content_start),
                    page_for(max(content_start, pending_end - 1)),
                    content_start,
                )
            )
        pending.clear()
        numbered = False

    position = 0
    for line in markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence is not None or fence_match:
            if fence is None:
                flush()
                pending_start = position
                fence = fence_match.group(1)
            elif (
                fence_match
                and fence_match.group(1)[0] == fence[0]
                and len(fence_match.group(1)) >= len(fence)
            ):
                pending.append(line)
                pending_end = position + len(line)
                flush()
                fence = None
                position += len(line) + 1
                continue
            pending.append(line)
            pending_end = position + len(line)
            position += len(line) + 1
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            del headings[level - 1 :]
            while len(headings) < level - 1:
                headings.append("")
            headings.append(heading.group(2).strip())
            position += len(line) + 1
            continue
        if _NUMBERED_CLAUSE.match(line):
            flush()
            numbered = True
        elif line.strip() and pending and not numbered and not pending[-1].strip():
            flush()
        if not pending:
            pending_start = position
        pending.append(line)
        if line.strip():
            pending_end = position + len(line)
        position += len(line) + 1
    flush()
    return tuple(blocks)


def _document_blocks(markdown: str) -> tuple[_Block, ...]:
    headings: list[str] = []
    blocks: list[_Block] = []
    pending: list[str] = []

    def flush() -> None:
        text = "\n".join(pending).strip()
        if text:
            blocks.append(_Block(text, " / ".join(headings) or None))
        pending.clear()

    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for line in lines:
        heading = _HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            del headings[level - 1 :]
            while len(headings) < level - 1:
                headings.append("")
            headings.append(heading.group(2).strip())
            continue
        if not line.strip():
            flush()
        else:
            pending.append(line.rstrip())
    flush()
    return tuple(blocks)


def _split_text_block(
    block: _Block, max_tokens: int, overlap_tokens: int
) -> tuple[_Block, ...]:
    matches = tuple(_TOKEN.finditer(block.text))
    if len(matches) <= max_tokens:
        return (block,)
    result: list[_Block] = []
    start = 0
    while start < len(matches):
        end = min(start + max_tokens, len(matches))
        char_start = matches[start].start()
        char_end = matches[end - 1].end()
        result.append(_Block(block.text[char_start:char_end], block.section_path))
        if end == len(matches):
            break
        start = end - overlap_tokens
    return tuple(result)


def _is_table(text: str) -> bool:
    lines = text.splitlines()
    return (
        len(lines) >= 2
        and "|" in lines[0]
        and _TABLE_SEPARATOR.match(lines[1]) is not None
    )


def _split_table(block: _Block, max_tokens: int) -> tuple[_Block, ...]:
    lines = block.text.splitlines()
    header = lines[:2]
    header_tokens = count_tokens("\n".join(header))
    if header_tokens >= max_tokens:
        return _split_text_block(block, max_tokens, 0)
    groups: list[_Block] = []
    current = list(header)
    current_tokens = header_tokens
    for row in lines[2:]:
        row_tokens = count_tokens(row)
        if len(current) > 2 and current_tokens + row_tokens > max_tokens:
            groups.append(_Block("\n".join(current), block.section_path))
            current = list(header)
            current_tokens = header_tokens
        if row_tokens + header_tokens > max_tokens:
            groups.extend(
                _split_text_block(_Block(row, block.section_path), max_tokens, 0)
            )
        else:
            current.append(row)
            current_tokens += row_tokens
    if len(current) > 2:
        groups.append(_Block("\n".join(current), block.section_path))
    return tuple(groups)


def _is_navigation_noise(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text).lower()
    return normalized in {"目录", "返回顶部", "tableofcontents", "backtotop"}


__all__ = ["chunk_document", "count_tokens", "parent_child_document"]
