-- 模块：aiep-biz-aihub
-- 影响表：ai_operation_conversation、ai_operation_message、ai_operation_run、ai_operation_artifact
-- 前置核验：执行 manual/M__1.0.0__operation_assistant_mvp_precheck.sql，确认目标库不存在同名表且版本号未使用。
-- 兼容性：仅新增表和索引，不修改现有对象；MySQL 8.0，utf8mb4。
-- 数据回填：无，MVP 从空表开始。
-- 回滚：rollback/R__V1.0.0__operation_assistant_mvp.sql；回滚会永久删除本功能数据。

CREATE TABLE ai_operation_conversation (
    id CHAR(36) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NULL,
    status VARCHAR(32) NOT NULL,
    last_research_run_id CHAR(36) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_operation_conversation_tenant_id (tenant_id, id),
    KEY idx_ai_operation_conversation_user_updated (tenant_id, user_id, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_operation_message (
    id CHAR(36) NOT NULL,
    conversation_id CHAR(36) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL,
    content LONGTEXT NOT NULL,
    run_id CHAR(36) NULL,
    client_request_id VARCHAR(128) NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_operation_message_request (tenant_id, client_request_id),
    KEY idx_ai_operation_message_conversation_created (conversation_id, created_at),
    KEY idx_ai_operation_message_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_operation_run (
    id CHAR(36) NOT NULL,
    conversation_id CHAR(36) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    user_message_id CHAR(36) NOT NULL,
    agent_run_id VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    last_event_sequence BIGINT NOT NULL DEFAULT 0,
    failure_code VARCHAR(128) NULL,
    failure_message VARCHAR(1000) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_operation_run_agent (agent_run_id),
    KEY idx_ai_operation_run_conversation_created (conversation_id, created_at),
    KEY idx_ai_operation_run_status_updated (status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_operation_artifact (
    id CHAR(36) NOT NULL,
    conversation_id CHAR(36) NOT NULL,
    run_id CHAR(36) NOT NULL,
    source_research_run_id CHAR(36) NULL,
    tenant_id VARCHAR(64) NOT NULL,
    artifact_type VARCHAR(64) NOT NULL,
    platform VARCHAR(64) NOT NULL,
    version_no INT NOT NULL,
    title VARCHAR(500) NOT NULL,
    body_markdown MEDIUMTEXT NOT NULL,
    body_html MEDIUMTEXT NULL,
    internal_metadata JSON NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_operation_artifact_version (conversation_id, artifact_type, version_no),
    KEY idx_ai_operation_artifact_run (run_id),
    KEY idx_ai_operation_artifact_conversation_created (conversation_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
