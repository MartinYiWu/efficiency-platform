"""原子语义上限、精确覆盖与证据反向核验。"""

import unicodedata
from collections.abc import Sequence

from efficiency_platform_agent.contracts.hr import (
    Assessment,
    Block,
    Evidence,
    Requirement,
)

from .interview import FORBIDDEN


def criterion_key(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def validate_evidence(evidence: Sequence[Evidence], blocks: Sequence[Block]) -> None:
    indexed = {b.block_id: b for b in blocks}
    if len(indexed) != len(blocks):
        raise ValueError("HR_FACT_EVIDENCE_DUPLICATE_BLOCK")
    for e in evidence:
        block = indexed.get(e.block_id)
        if block is None or e.end <= e.start or block.text[e.start : e.end] != e.quote:
            raise ValueError("HR_FACT_EVIDENCE_INVALID")


def semantic_batches(
    requirements: Sequence[Requirement] | list[dict[str, str]],
) -> list[list[Requirement]]:
    items = [
        x if isinstance(x, Requirement) else Requirement.model_validate(x)
        for x in requirements
    ]
    if len({x.requirement_id for x in items}) != len(items):
        raise ValueError("HR_EVALUATION_DUPLICATE_ID")
    unique: dict[str, Requirement] = {}
    for item in items:
        key = criterion_key(item.criterion)
        unique.setdefault(key, item)
    if len(unique) > 60:
        raise ValueError("HR_EVALUATION_WORK_LIMIT_EXCEEDED")
    values = list(unique.values())
    return [values[i : i + 15] for i in range(0, len(values), 15)]


def validate_assessments(
    requirements: Sequence[Requirement],
    assessments: Sequence[Assessment],
    blocks: Sequence[Block],
) -> None:
    expected = {r.requirement_id for r in requirements}
    actual = [a.requirement_id for a in assessments]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("HR_EVALUATION_COVERAGE_INVALID")
    for item in assessments:
        if any(word in item.reason for word in FORBIDDEN):
            raise ValueError("HR_EVALUATION_PROTECTED_ATTRIBUTE")
        validate_evidence(item.evidence, blocks)
