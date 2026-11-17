"""按Unicode字符边界分片，并保留原始块定位。"""

from hashlib import sha256

from efficiency_platform_agent.contracts.hr import Block


def split_fact_blocks(
    blocks: list[Block],
) -> tuple[list[list[Block]], dict[str, tuple[str, int]]]:
    if len({b.block_id for b in blocks}) != len(blocks):
        raise ValueError("HR_FACT_EVIDENCE_DUPLICATE_BLOCK")
    chunks: list[list[Block]] = [[]]
    mapping: dict[str, tuple[str, int]] = {}
    chunk_size = 0
    for block in blocks:
        start = 0
        while start < len(block.text) or (start == 0 and not block.text):
            piece_id = (
                "segment-"
                + sha256(f"{block.block_id}:{start}".encode()).hexdigest()[:32]
            )
            low, high = start + 1, len(block.text)
            end = start
            while low <= high:
                middle = (low + high) // 2
                piece = block.model_copy(
                    update={
                        "block_id": piece_id,
                        "text": block.text[start:middle],
                        "offsets": [],
                        "source_start": block.source_start + start,
                    }
                )
                if len(piece.model_dump_json().encode()) <= 32 * 1024:
                    end = middle
                    low = middle + 1
                else:
                    high = middle - 1
            if end == start and block.text:
                raise ValueError("HR_FACT_BLOCK_TOO_LARGE")
            if end < len(block.text):
                boundary = max(
                    block.text.rfind(delimiter, start, end)
                    for delimiter in ("\n", "。", "；", ";", ". ")
                )
                if boundary > start + (end - start) // 2:
                    end = boundary + 1
            piece = block.model_copy(
                update={
                    "block_id": piece_id,
                    "text": block.text[start:end],
                    "offsets": [],
                    "source_start": block.source_start + start,
                }
            )
            size = len(piece.model_dump_json().encode())
            if chunk_size + size > 36 * 1024:
                chunks.append([])
                chunk_size = 0
            chunks[-1].append(piece)
            mapping[piece_id] = (block.block_id, start)
            chunk_size += size
            if not block.text:
                break
            start = end
    if len(chunks) > 12:
        raise ValueError("HR_EVALUATION_WORK_LIMIT_EXCEEDED")
    return chunks, mapping
