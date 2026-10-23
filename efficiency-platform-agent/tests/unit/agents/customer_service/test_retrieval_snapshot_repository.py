"""生产 MySQL 检索快照保留证据处理事实。"""

import json
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_evidence_assembly import group_fixture

from efficiency_platform_agent.agents.customer_service.conflict_screen import (
    ConflictPair,
    ConflictScreen,
)
from efficiency_platform_agent.agents.customer_service.evidence_assembly import (
    assemble_evidence,
)
from efficiency_platform_agent.agents.customer_service.retrieval import RetrievalTrace
from efficiency_platform_agent.agents.customer_service.retrieval_snapshot_repository import (
    MySqlRetrievalSnapshotRepository,
)
from efficiency_platform_agent.agents.customer_service.service import (
    CustomerServiceRunService,
)
from efficiency_platform_agent.agents.customer_service.state import (
    AnswerMode,
    SufficiencyDecision,
)


class RecordingEngine:
    def __init__(self):
        self.calls = []

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_mysql_snapshot_persists_task4_facts_and_exclusions(legacy):
    children, parents = group_fixture()
    assembly = assemble_evidence(
        children,
        parents,
        context_token_limit=30,
        reserved_tokens=0,
        final_evidence_top_k=3,
        adjacent_group_max_parents=2,
    )
    assembly = replace(
        assembly,
        grouping_reasons={parents[2].parent_id: "TABLE_IDENTITY_UNAVAILABLE"},
    )
    trace = RetrievalTrace(
        original_query="问题",
        rewritten_queries=(),
        index_release_ids=(parents[0].index_release_id,),
        vector_candidates=children,
        fts_candidates=(),
        fused_candidates=children,
        reranked_evidence=children,
        assembly=None if legacy else assembly,
        conflict_screen=None
        if legacy
        else ConflictScreen(
            pairs=(
                ConflictPair(
                    left_parent_id=parents[0].parent_id,
                    right_parent_id=parents[1].parent_id,
                    same_scope=True,
                    verdict="CONFLICT",
                    left_quote=parents[0].content,
                    right_quote=parents[1].content,
                    reason="适用范围相同但规定不同",
                ),
            ),
            errors=("CONFLICT_QUOTE_INVALID",),
            blocked=True,
        ),
    )
    result = SimpleNamespace(
        retrieval_trace=trace,
        sufficiency=SufficiencyDecision(
            sufficient=False,
            supported_claims=(),
            unsupported_claims=(),
            conflicts=(),
            recommended_mode=AnswerMode.INSUFFICIENT_EVIDENCE,
        ),
    )
    engine = RecordingEngine()
    await MySqlRetrievalSnapshotRepository(engine).save(uuid4(), result)
    assert len(engine.calls) == 1
    sql, params = engine.calls[0]
    assert "retrieval_facts_json" in sql
    assert "CAST(:retrieval_facts AS JSON)" in sql
    assert "ON DUPLICATE KEY UPDATE id=id" in sql
    saved = json.loads(params["retrieval_facts"])
    public_debug = CustomerServiceRunService._retrieval_facts(result)
    keys = {
        "final_parent_candidates",
        "evidence_groups",
        "grouping_decisions",
        "conflict_screen",
        "assembly_decisions",
    }
    assert set(saved) == keys
    assert saved == {key: public_debug[key] for key in keys}
    if legacy:
        assert saved["conflict_screen"] is None
        assert saved["assembly_decisions"] == []
    else:
        assert saved["final_parent_candidates"] == [
            str(p.parent_id) for p in parents[:3]
        ]
        assert saved["evidence_groups"][0]["parent_ids"] == [
            str(p.parent_id) for p in parents[:2]
        ]
        assert {d["reason"] for d in saved["assembly_decisions"]} == {
            "SELECTED",
            "BUDGET_EXCLUDED",
            "FINAL_TOP_K_EXCLUDED",
        }
        assert saved["conflict_screen"]["errors"] == ["CONFLICT_QUOTE_INVALID"]
        assert saved["conflict_screen"]["pairs"][0]["left_quote"] == parents[0].content
        assert saved["conflict_screen"]["pairs"][0]["verdict"] == "CONFLICT"


@pytest.mark.asyncio
async def test_mysql_snapshot_does_not_create_facts_without_retrieval():
    engine = RecordingEngine()
    await MySqlRetrievalSnapshotRepository(engine).save(
        uuid4(), SimpleNamespace(retrieval_trace=None, sufficiency=None)
    )
    assert engine.calls == []
