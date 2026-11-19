"""权限内两路有限RRF融合；不因数量不足扩大候选范围。"""

from efficiency_platform_agent.core.memory_index import (
    MemoryIndexIdentity,
    MemoryRecallCandidate,
)


def fuse_memory_candidates(
    vector: tuple[MemoryRecallCandidate, ...],
    lexical: tuple[MemoryRecallCandidate, ...],
    allowed: tuple[MemoryIndexIdentity, ...],
    *,
    top_k: int = 8,
) -> tuple[MemoryRecallCandidate, ...]:
    if type(top_k) is not int or not 1 <= top_k <= 8:
        raise ValueError("MEMORY_RECALL_TOPK_INVALID")
    legal = frozenset(allowed)
    scores: dict[MemoryIndexIdentity, float] = {}
    for channel in (vector, lexical):
        if type(channel) is not tuple or len(channel) > 30:
            raise ValueError("MEMORY_RECALL_CANDIDATE_LIMIT")
        seen: set[MemoryIndexIdentity] = set()
        for rank, candidate in enumerate(channel, 1):
            if (
                type(candidate) is not MemoryRecallCandidate
                or candidate.identity not in legal
            ):
                raise ValueError("MEMORY_RECALL_SCOPE_DENIED")
            if candidate.identity in seen:
                raise ValueError("MEMORY_RECALL_DUPLICATE_CANDIDATE")
            seen.add(candidate.identity)
            scores[candidate.identity] = scores.get(candidate.identity, 0.0) + 1 / (
                60 + rank
            )
    ordered = sorted(
        scores,
        key=lambda item: (
            -scores[item],
            item.item_id,
            item.version_id,
            item.generation,
        ),
    )
    return tuple(MemoryRecallCandidate(item, scores[item]) for item in ordered[:top_k])
