CREATE TABLE agent_run (
    run_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL,
    request_id VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    version BIGINT NOT NULL,
    state_json JSON NOT NULL,
    created_at_epoch_ms BIGINT NOT NULL,
    updated_at_epoch_ms BIGINT NOT NULL,
    PRIMARY KEY (run_id),
    UNIQUE KEY uk_agent_run_tenant_request (tenant_id, request_id),
    KEY idx_agent_run_tenant_status_updated (tenant_id, status, updated_at_epoch_ms)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE agent_request_deduplication (
    tenant_id VARCHAR(128) NOT NULL,
    request_id VARCHAR(128) NOT NULL,
    run_id VARCHAR(128) NOT NULL,
    created_at_epoch_ms BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, request_id),
    UNIQUE KEY uk_agent_request_deduplication_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE agent_run_event (
    event_id VARCHAR(128) NOT NULL,
    run_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL,
    sequence_no BIGINT NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    occurred_at_epoch_ms BIGINT NOT NULL,
    event_json JSON NOT NULL,
    PRIMARY KEY (event_id),
    UNIQUE KEY uk_agent_run_event_sequence (run_id, sequence_no),
    KEY idx_agent_run_event_tenant_run_sequence (tenant_id, run_id, sequence_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
