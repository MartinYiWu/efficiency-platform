-- 智能客服 RAG 真实评测闭环。业务关联使用逻辑引用，不创建物理外键。

CREATE TABLE ai_rag_eval_dataset (
    id CHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description VARCHAR(2000) NULL,
    agent_key VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_ai_rag_eval_dataset_agent_status (agent_key, status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_rag_eval_case (
    id CHAR(36) NOT NULL,
    dataset_id CHAR(36) NOT NULL,
    case_no VARCHAR(128) NOT NULL,
    question TEXT NOT NULL,
    expected_answer_mode VARCHAR(32) NOT NULL,
    expected_facts JSON NOT NULL,
    prohibited_facts JSON NOT NULL,
    expected_document_titles JSON NOT NULL,
    expected_document_version_ids JSON NOT NULL,
    min_citation_count INT NOT NULL DEFAULT 0,
    tags JSON NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_rag_eval_case_no (dataset_id, case_no),
    KEY idx_ai_rag_eval_case_dataset_enabled (dataset_id, enabled, case_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_rag_eval_run (
    id CHAR(36) NOT NULL,
    dataset_id CHAR(36) NOT NULL,
    agent_key VARCHAR(128) NOT NULL,
    agent_version_id CHAR(36) NOT NULL,
    rag_policy_version_id CHAR(36) NOT NULL,
    knowledge_bindings JSON NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_count INT NOT NULL DEFAULT 0,
    passed_count INT NOT NULL DEFAULT 0,
    failed_count INT NOT NULL DEFAULT 0,
    metrics_json JSON NULL,
    failure_code VARCHAR(128) NULL,
    failure_message VARCHAR(1000) NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    started_at DATETIME(6) NULL,
    finished_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    KEY idx_ai_rag_eval_run_dataset_created (dataset_id, created_at),
    KEY idx_ai_rag_eval_run_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_rag_eval_case_result (
    id CHAR(36) NOT NULL,
    run_id CHAR(36) NOT NULL,
    case_id CHAR(36) NOT NULL,
    debug_run_id CHAR(36) NULL,
    execution_status VARCHAR(32) NOT NULL,
    passed TINYINT(1) NOT NULL,
    latency_ms BIGINT NOT NULL,
    answer_mode VARCHAR(32) NULL,
    answer_markdown LONGTEXT NULL,
    citations_json JSON NULL,
    metrics_json JSON NULL,
    error_code VARCHAR(128) NULL,
    error_message VARCHAR(1000) NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_rag_eval_result_case (run_id, case_id),
    KEY idx_ai_rag_eval_result_run_passed (run_id, passed),
    KEY idx_ai_rag_eval_result_debug (debug_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
