CREATE TABLE ai_agent_version_policy_binding (
    agent_version_id CHAR(36) NOT NULL,
    model_policy_id CHAR(36) NULL,
    rag_policy_id CHAR(36) NULL,
    PRIMARY KEY (agent_version_id),
    KEY idx_ai_agent_policy_model (model_policy_id),
    KEY idx_ai_agent_policy_rag (rag_policy_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO ai_agent_version_policy_binding (agent_version_id, model_policy_id, rag_policy_id)
VALUES (
    '11000000-0000-0000-0000-000000000001',
    '12000000-0000-0000-0000-000000000001',
    '13000000-0000-0000-0000-000000000001'
);
