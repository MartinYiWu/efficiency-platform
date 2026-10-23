"""智能客服检索快照持久化，仅保存结构化事实。"""

from __future__ import annotations

import json
import time
from typing import Any, Protocol
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from .graph import GraphResult
from .retrieval import RetrievalTrace

_SNAPSHOT_NAMESPACE = UUID("997e5350-2269-433a-b6a7-f7719d2831ca")


class RetrievalSnapshotRepository(Protocol):
    async def save(self, run_id: UUID, result: GraphResult) -> None: ...


class InMemoryRetrievalSnapshotRepository:
    def __init__(self) -> None:
        self.values: dict[UUID, GraphResult] = {}

    async def save(self, run_id: UUID, result: GraphResult) -> None:
        if result.retrieval_trace is not None:
            self.values[run_id] = result


class MySqlRetrievalSnapshotRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def save(self, run_id: UUID, result: GraphResult) -> None:
        trace = result.retrieval_trace
        if trace is None or result.sufficiency is None:
            return
        payload = {
            "id": str(uuid5(_SNAPSHOT_NAMESPACE, f"{run_id}:retrieval")),
            "run_id": str(run_id),
            "index_release_ids": json.dumps(
                [str(item) for item in trace.index_release_ids], ensure_ascii=False
            ),
            "original_query": trace.original_query,
            "rewritten_queries": json.dumps(
                list(trace.rewritten_queries), ensure_ascii=False
            ),
            "vector_candidates": _evidence_json(trace.vector_candidates),
            "fts_candidates": _evidence_json(trace.fts_candidates),
            "fused_candidates": _evidence_json(trace.fused_candidates),
            "reranked_evidence": _evidence_json(trace.reranked_evidence),
            "sufficiency": result.sufficiency.model_dump_json(),
            "retrieval_facts": json.dumps(
                evidence_processing_facts(trace), ensure_ascii=False
            ),
            "created_at": int(time.time() * 1000),
        }
        async with self.engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO agent_customer_service_retrieval_snapshot "
                    "(id,run_id,stage_key,index_release_ids_json,original_query,"
                    "rewritten_queries_json,vector_candidates_json,fts_candidates_json,"
                    "fused_candidates_json,reranked_evidence_json,sufficiency_json,"
                    "retrieval_facts_json,"
                    "created_at_epoch_ms) VALUES "
                    "(:id,:run_id,'retrieval',CAST(:index_release_ids AS JSON),"
                    ":original_query,CAST(:rewritten_queries AS JSON),"
                    "CAST(:vector_candidates AS JSON),CAST(:fts_candidates AS JSON),"
                    "CAST(:fused_candidates AS JSON),CAST(:reranked_evidence AS JSON),"
                    "CAST(:sufficiency AS JSON),CAST(:retrieval_facts AS JSON),:created_at) "
                    "ON DUPLICATE KEY UPDATE id=id"
                ),
                payload,
            )


def evidence_processing_facts(trace: RetrievalTrace | None) -> dict[str, Any]:
    """调试输出与生产快照共享同一组证据处理事实。"""
    assembly = trace.assembly if trace else None
    selected = {p.parent_id for p in assembly.selected} if assembly else set()
    return {
        "final_parent_candidates": [
            str(p.parent_id) for p in (assembly.candidate_parents if assembly else ())
        ],
        "evidence_groups": [
            g.model_dump(mode="json") for g in (assembly.groups if assembly else ())
        ],
        "grouping_decisions": [
            {"parent_id": str(pid), "reason": reason}
            for pid, reason in (assembly.grouping_reasons.items() if assembly else ())
        ],
        "conflict_screen": trace.conflict_screen.model_dump(mode="json")
        if trace and trace.conflict_screen
        else None,
        "assembly_decisions": [
            {
                "parent_id": str(pid),
                "selected": pid in selected,
                "reason": "SELECTED"
                if pid in selected
                else (
                    "DUPLICATE_PARENT_CONTENT"
                    if pid in assembly.duplicate_parent_ids
                    else assembly.exclusion_reasons.get(pid, "CONTEXT_BUDGET_EXCEEDED")
                ),
            }
            for pid in (assembly.hit_chunk_ids if assembly else {})
        ],
    }


def _evidence_json(values: tuple[object, ...]) -> str:
    return json.dumps(
        [item.model_dump(mode="json") for item in values],  # type: ignore[attr-defined]
        ensure_ascii=False,
    )


__all__ = [
    "InMemoryRetrievalSnapshotRepository",
    "MySqlRetrievalSnapshotRepository",
    "RetrievalSnapshotRepository",
]
