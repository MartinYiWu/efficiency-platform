"""批量核对减少请求，但每一对证据仍需完整、唯一、逐字核验。"""

from itertools import combinations
from uuid import uuid4

import pytest
from test_evidence_assembly import group_fixture

from efficiency_platform_agent.agents.customer_service.conflict_screen import (
    screen_conflicts,
)


def parents_and_members():
    _, source = group_fixture()
    parents = tuple(
        source[0].model_copy(
            update={
                "parent_id": uuid4(),
                "document_id": uuid4(),
                "content": f"第{index}项真实规则",
            }
        )
        for index in range(4)
    )
    members = {
        (p.knowledge_base_id, p.document_id, p.document_version_id, p.index_release_id)
        for p in parents
    }
    return parents, members


class Gateway:
    def __init__(self, mutation=None):
        self.calls = []
        self.mutation = mutation

    async def complete(self, stage, value, output_type):
        self.calls.append(value)
        by_id = {p["parent_id"]: p for p in value["evidence"]}
        results = [
            {
                "left_parent_id": pair["left_parent_id"],
                "right_parent_id": pair["right_parent_id"],
                "same_scope": False,
                "verdict": "NO_CONFLICT",
                "left_quote": by_id[pair["left_parent_id"]]["content"],
                "right_quote": by_id[pair["right_parent_id"]]["content"],
                "reason": "原文对象不同",
            }
            for pair in value["comparison_pairs"]
        ]
        if self.mutation == "missing":
            results.pop()
        if self.mutation == "duplicate":
            results[-1] = results[0]
        if self.mutation == "quote":
            results[0]["left_quote"] = "伪造原文"
        if self.mutation == "identity":
            results[0]["left_parent_id"] = str(uuid4())
        if self.mutation == "conflict":
            results[0].update(same_scope=True, verdict="CONFLICT")
        if self.mutation == "uncertain":
            results[0]["verdict"] = "UNCERTAIN"
        return output_type.model_validate({"pairs": list(reversed(results))})


async def test_batches_cover_all_pairs_once_and_restore_trusted_order():
    parents, members = parents_and_members()
    gateway = Gateway()
    result = await screen_conflicts(
        parents,
        question="问题",
        gateway=gateway,
        members=members,
        stage_bound=True,
        batch_enabled=True,
    )
    assert not result.blocked
    assert len(gateway.calls) == 2
    assert [(p.left_parent_id, p.right_parent_id) for p in result.pairs] == [
        (l.parent_id, r.parent_id) for l, r in combinations(parents, 2)
    ]
    assert all(len(call["comparison_pairs"]) == 3 for call in gateway.calls)


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "quote", "identity", "conflict", "uncertain"]
)
async def test_any_unverified_or_conflicting_pair_still_blocks(mutation):
    parents, members = parents_and_members()
    result = await screen_conflicts(
        parents,
        question="问题",
        gateway=Gateway(mutation),
        members=members,
        stage_bound=True,
        batch_enabled=True,
    )
    assert result.blocked
    if mutation not in {"conflict", "uncertain"}:
        assert result.errors


async def test_batching_never_weakens_membership_or_prompt_binding():
    parents, members = parents_and_members()
    for valid_members, bound in [(set(), True), (members, False)]:
        gateway = Gateway()
        result = await screen_conflicts(
            parents,
            question="问题",
            gateway=gateway,
            members=valid_members,
            stage_bound=bound,
            batch_enabled=True,
        )
        assert result.blocked and not gateway.calls
