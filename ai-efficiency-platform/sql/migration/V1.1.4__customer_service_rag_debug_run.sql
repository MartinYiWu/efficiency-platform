CREATE TABLE IF NOT EXISTS ai_rag_debug_run (
    id CHAR(36) NOT NULL,
    agent_key VARCHAR(128) NOT NULL,
    agent_version_id CHAR(36) NOT NULL,
    rag_policy_version_id CHAR(36) NOT NULL,
    question TEXT NOT NULL,
    request_json JSON NOT NULL,
    response_json JSON NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_ai_rag_debug_agent_created (agent_key, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
