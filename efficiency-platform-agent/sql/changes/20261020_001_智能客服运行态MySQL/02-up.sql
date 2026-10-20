-- 智能客服 Agent 运行态增量；执行前必须通过 01-precheck.sql。
CREATE TABLE agent_release_bundle (
    release_id VARCHAR(128) NOT NULL,
    agent_key VARCHAR(128) NOT NULL,
    agent_version VARCHAR(64) NOT NULL,
    graph_version VARCHAR(64) NOT NULL,
    environment VARCHAR(32) NOT NULL,
    snapshot_json JSON NOT NULL,
    checksum CHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at_epoch_ms BIGINT NOT NULL,
    PRIMARY KEY (release_id),
    KEY idx_agent_release_bundle_active (agent_key, environment, status),
    KEY idx_agent_release_bundle_checksum (checksum)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE agent_customer_service_retrieval_snapshot (
    id VARCHAR(128) NOT NULL,
    run_id VARCHAR(128) NOT NULL,
    stage_key VARCHAR(128) NOT NULL,
    index_release_ids_json JSON NOT NULL,
    original_query LONGTEXT NOT NULL,
    rewritten_queries_json JSON NOT NULL,
    vector_candidates_json JSON NOT NULL,
    fts_candidates_json JSON NOT NULL,
    fused_candidates_json JSON NOT NULL,
    reranked_evidence_json JSON NOT NULL,
    sufficiency_json JSON NOT NULL,
    created_at_epoch_ms BIGINT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_cs_retrieval_run_stage (run_id, stage_key),
    KEY idx_agent_cs_retrieval_created (created_at_epoch_ms)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
