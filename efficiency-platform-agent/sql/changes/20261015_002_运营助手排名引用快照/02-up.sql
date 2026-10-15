CREATE TABLE agent_ranked_reference_snapshot (
    id BIGINT NOT NULL AUTO_INCREMENT,
    tenant_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    conversation_id VARCHAR(64) NOT NULL,
    source_run_id VARCHAR(64) NOT NULL,
    contract_version VARCHAR(32) NOT NULL,
    deliverable_json JSON NOT NULL,
    content_hash CHAR(64) NOT NULL,
    created_at_epoch_ms BIGINT NOT NULL,
    expires_at_epoch_ms BIGINT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_ranked_reference_identity (
        tenant_id, user_id, conversation_id, source_run_id
    ),
    KEY idx_agent_ranked_reference_conversation_created (
        tenant_id, conversation_id, created_at_epoch_ms
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
