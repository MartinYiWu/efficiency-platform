"""真实隔离MySQL检索快照擦除；owner/join证明另由服务和完整生命周期验证。"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from efficiency_platform_agent.agents.customer_service.retrieval_snapshot_repository import (
    MySqlRetrievalSnapshotRepository,
)
from tests.integration.context_control.test_memory_execution_mysql import configured_url

pytestmark = pytest.mark.skipif(
    os.environ.get("MEMORY_IT_ENABLED") != "1", reason="须root显式本机隔离MySQL"
)


async def test_real_snapshot_erasure_removes_all_stages_and_preserves_other_run():
    engine = create_async_engine(configured_url())
    erased, other = uuid4(), uuid4()
    try:
        async with engine.begin() as connection:
            for run in (erased, other):
                for stage in ("retrieval", "additional-stage"):
                    await connection.execute(
                        text(
                            "INSERT INTO agent_customer_service_retrieval_snapshot(id,run_id,stage_key,index_release_ids_json,original_query,rewritten_queries_json,vector_candidates_json,fts_candidates_json,fused_candidates_json,reranked_evidence_json,sufficiency_json,created_at_epoch_ms) VALUES(:id,:run,:stage,JSON_ARRAY(),:body,JSON_ARRAY(),JSON_ARRAY(),JSON_ARRAY(),JSON_ARRAY(),JSON_ARRAY(),JSON_OBJECT(),1)"
                        ),
                        {
                            "id": str(uuid4()),
                            "run": str(run),
                            "stage": stage,
                            "body": "SYNTHETIC_SNAPSHOT_BODY",
                        },
                    )
        repository = MySqlRetrievalSnapshotRepository(engine)
        assert await repository.erase_run(erased) is True
        assert await repository.erase_run(erased) is True
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text(
                        "SELECT COUNT(*) FROM agent_customer_service_retrieval_snapshot WHERE run_id=:run"
                    ),
                    {"run": str(erased)},
                )
                == 0
            )
            assert (
                await connection.scalar(
                    text(
                        "SELECT COUNT(*) FROM agent_customer_service_retrieval_snapshot WHERE run_id=:run AND original_query=:body"
                    ),
                    {"run": str(other), "body": "SYNTHETIC_SNAPSHOT_BODY"},
                )
                == 2
            )
    finally:
        await engine.dispose()
