"""按标题、段落、列表和表格边界执行确定性分块。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from .contracts import ChunkDraft, ParsedDocument

_TOKEN = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u9fff]|[^\s]", re.UNICODE)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}")


@dataclass(frozen=True, slots=True)
class _Block:
    text: str
    section_path: str | None
    page_no: int | None = None


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


__all__ = ["chunk_document", "count_tokens"]
