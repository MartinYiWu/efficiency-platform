-- 模块：aiep-platform-file、aiep-biz-knowledge、aiep-biz-aihub、aiep-biz-system
-- 影响：仅新增 AI 智能客服首个闭环所需表和索引，不修改既有对象。
-- 前置核验：先执行 manual/M__1.1.0__customer_service_knowledge_aihub_precheck.sql。
-- 数据库：MySQL 8.0，utf8mb4；业务关联均为逻辑引用，不创建物理外键。
-- 回滚：rollback/R__V1.1.0__customer_service_knowledge_aihub.sql 会删除本迁移全部数据。

CREATE TABLE pf_file_object (
    id CHAR(36) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    storage_provider VARCHAR(32) NOT NULL,
    object_key VARCHAR(512) NOT NULL,
    original_name VARCHAR(500) NOT NULL,
    content_type VARCHAR(128) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_pf_file_object_provider_key (storage_provider, object_key),
    KEY idx_pf_file_object_tenant_sha256 (tenant_id, sha256),
    KEY idx_pf_file_object_tenant_status_created (tenant_id, status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE kb_knowledge_base (
    id CHAR(36) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    code VARCHAR(128) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description VARCHAR(2000) NULL,
    knowledge_type VARCHAR(32) NOT NULL,
    visibility_scope VARCHAR(32) NOT NULL,
    owner_department_id VARCHAR(64) NULL,
    status VARCHAR(32) NOT NULL,
    current_index_release_id CHAR(36) NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_by VARCHAR(64) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_kb_knowledge_base_tenant_code (tenant_id, code),
    KEY idx_kb_knowledge_base_tenant_status (tenant_id, status),
    KEY idx_kb_knowledge_base_current_release (current_index_release_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE kb_directory (
    id CHAR(36) NOT NULL,
    knowledge_base_id CHAR(36) NOT NULL,
    parent_id CHAR(36) NULL,
    name VARCHAR(255) NOT NULL,
    path VARCHAR(2000) NOT NULL,
    sort_no INT NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_by VARCHAR(64) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_kb_directory_parent_name (knowledge_base_id, parent_id, name),
    KEY idx_kb_directory_base_parent_sort (knowledge_base_id, parent_id, sort_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE kb_document (
    id CHAR(36) NOT NULL,
    knowledge_base_id CHAR(36) NOT NULL,
    directory_id CHAR(36) NULL,
    title VARCHAR(500) NOT NULL,
    document_code VARCHAR(128) NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    current_published_version_id CHAR(36) NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_by VARCHAR(64) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_kb_document_base_code (knowledge_base_id, document_code),
    KEY idx_kb_document_directory_status (knowledge_base_id, directory_id, status),
    KEY idx_kb_document_current_version (current_published_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE kb_document_version (
    id CHAR(36) NOT NULL,
    document_id CHAR(36) NOT NULL,
    version_no INT NOT NULL,
    file_id CHAR(36) NOT NULL,
    file_sha256 CHAR(64) NOT NULL,
    content_type VARCHAR(128) NOT NULL,
    change_summary VARCHAR(500) NULL,
    effective_date DATE NULL,
    status VARCHAR(32) NOT NULL,
    parse_metadata JSON NULL,
    error_code VARCHAR(128) NULL,
    error_message VARCHAR(1000) NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    published_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_kb_document_version_no (document_id, version_no),
    KEY idx_kb_document_version_status_created (status, created_at),
    KEY idx_kb_document_version_file (file_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE kb_ingest_batch (
    id CHAR(36) NOT NULL,
    knowledge_base_id CHAR(36) NOT NULL,
    import_mode VARCHAR(32) NOT NULL,
    total_count INT NOT NULL,
    succeeded_count INT NOT NULL DEFAULT 0,
    failed_count INT NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    finished_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    KEY idx_kb_ingest_batch_base_created (knowledge_base_id, created_at),
    KEY idx_kb_ingest_batch_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE kb_ingest_item (
    id CHAR(36) NOT NULL,
    batch_id CHAR(36) NOT NULL,
    file_id CHAR(36) NULL,
    document_id CHAR(36) NULL,
    document_version_id CHAR(36) NULL,
    status VARCHAR(32) NOT NULL,
    error_code VARCHAR(128) NULL,
    error_message VARCHAR(1000) NULL,
    retry_of_item_id CHAR(36) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    finished_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    KEY idx_kb_ingest_item_batch_status (batch_id, status),
    KEY idx_kb_ingest_item_version (document_version_id),
    KEY idx_kb_ingest_item_retry (retry_of_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE kb_processing_task (
    id CHAR(36) NOT NULL,
    document_version_id CHAR(36) NOT NULL,
    agent_task_id VARCHAR(128) NULL,
    stage VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_no INT NOT NULL,
    progress_percent INT NOT NULL DEFAULT 0,
    error_code VARCHAR(128) NULL,
    error_message VARCHAR(1000) NULL,
    started_at DATETIME(6) NULL,
    finished_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_kb_processing_task_attempt (document_version_id, attempt_no),
    UNIQUE KEY uk_kb_processing_task_agent (agent_task_id),
    KEY idx_kb_processing_task_status_updated (status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE kb_index_release (
    id CHAR(36) NOT NULL,
    knowledge_base_id CHAR(36) NOT NULL,
    release_no INT NOT NULL,
    status VARCHAR(32) NOT NULL,
    document_count INT NOT NULL DEFAULT 0,
    chunk_count INT NOT NULL DEFAULT 0,
    embedding_model VARCHAR(128) NOT NULL,
    embedding_dimension INT NOT NULL,
    checksum CHAR(64) NOT NULL,
    previous_release_id CHAR(36) NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    published_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_kb_index_release_no (knowledge_base_id, release_no),
    KEY idx_kb_index_release_base_status (knowledge_base_id, status),
    KEY idx_kb_index_release_previous (previous_release_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE kb_index_release_document (
    index_release_id CHAR(36) NOT NULL,
    document_id CHAR(36) NOT NULL,
    document_version_id CHAR(36) NOT NULL,
    document_sha256 CHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (index_release_id, document_id),
    KEY idx_kb_index_release_document_version (document_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_agent_definition (
    id CHAR(36) NOT NULL,
    agent_key VARCHAR(128) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description VARCHAR(2000) NULL,
    agent_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_by VARCHAR(64) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_agent_definition_key (agent_key),
    KEY idx_ai_agent_definition_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_agent_version (
    id CHAR(36) NOT NULL,
    agent_definition_id CHAR(36) NOT NULL,
    semantic_version VARCHAR(64) NOT NULL,
    graph_key VARCHAR(128) NOT NULL,
    graph_version VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    change_summary VARCHAR(1000) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    published_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_agent_version_semver (agent_definition_id, semantic_version),
    KEY idx_ai_agent_version_status (agent_definition_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_prompt_definition (
    id CHAR(36) NOT NULL,
    prompt_key VARCHAR(160) NOT NULL,
    scope VARCHAR(32) NOT NULL,
    owner_agent_definition_id CHAR(36) NULL,
    name VARCHAR(255) NOT NULL,
    description VARCHAR(2000) NULL,
    stage_key VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_by VARCHAR(64) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_prompt_definition_key (prompt_key),
    KEY idx_ai_prompt_definition_owner_scope (owner_agent_definition_id, scope, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_prompt_version (
    id CHAR(36) NOT NULL,
    prompt_definition_id CHAR(36) NOT NULL,
    semantic_version VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    checksum CHAR(64) NOT NULL,
    change_summary VARCHAR(1000) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    published_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_prompt_version_semver (prompt_definition_id, semantic_version),
    KEY idx_ai_prompt_version_status (prompt_definition_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_prompt_message_template (
    id CHAR(36) NOT NULL,
    prompt_version_id CHAR(36) NOT NULL,
    ordinal INT NOT NULL,
    role VARCHAR(32) NOT NULL,
    message_key VARCHAR(128) NOT NULL,
    content_template LONGTEXT NOT NULL,
    content_format VARCHAR(32) NOT NULL,
    trusted_instruction TINYINT(1) NOT NULL,
    checksum CHAR(64) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_prompt_message_ordinal (prompt_version_id, ordinal),
    UNIQUE KEY uk_ai_prompt_message_key (prompt_version_id, message_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_prompt_variable (
    id CHAR(36) NOT NULL,
    prompt_message_template_id CHAR(36) NOT NULL,
    variable_name VARCHAR(128) NOT NULL,
    value_type VARCHAR(32) NOT NULL,
    value_source VARCHAR(64) NOT NULL,
    required TINYINT(1) NOT NULL,
    `sensitive` TINYINT(1) NOT NULL,
    max_length INT NULL,
    allow_untrusted_content TINYINT(1) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_prompt_variable_name (prompt_message_template_id, variable_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_agent_version_prompt_binding (
    agent_version_id CHAR(36) NOT NULL,
    stage_key VARCHAR(128) NOT NULL,
    ordinal INT NOT NULL,
    prompt_definition_id CHAR(36) NOT NULL,
    prompt_version_id CHAR(36) NOT NULL,
    required TINYINT(1) NOT NULL,
    PRIMARY KEY (agent_version_id, stage_key, ordinal),
    UNIQUE KEY uk_ai_agent_prompt_version (agent_version_id, prompt_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_model_policy (
    id CHAR(36) NOT NULL,
    owner_agent_definition_id CHAR(36) NOT NULL,
    policy_key VARCHAR(128) NOT NULL,
    semantic_version VARCHAR(64) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    model_name VARCHAR(128) NOT NULL,
    temperature DECIMAL(5,4) NOT NULL,
    top_p DECIMAL(5,4) NOT NULL,
    max_input_tokens INT NOT NULL,
    max_output_tokens INT NOT NULL,
    connect_timeout_ms INT NOT NULL,
    read_timeout_ms INT NOT NULL,
    max_retries INT NOT NULL,
    status VARCHAR(32) NOT NULL,
    checksum CHAR(64) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    published_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_model_policy_version (owner_agent_definition_id, policy_key, semantic_version),
    KEY idx_ai_model_policy_status (owner_agent_definition_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_rag_policy (
    id CHAR(36) NOT NULL,
    owner_agent_definition_id CHAR(36) NOT NULL,
    policy_key VARCHAR(128) NOT NULL,
    semantic_version VARCHAR(64) NOT NULL,
    rewrite_query_limit INT NOT NULL,
    vector_top_k INT NOT NULL,
    fts_top_k INT NOT NULL,
    fusion_top_k INT NOT NULL,
    rerank_top_k INT NOT NULL,
    context_token_limit INT NOT NULL,
    citation_limit INT NOT NULL,
    status VARCHAR(32) NOT NULL,
    checksum CHAR(64) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    published_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_rag_policy_version (owner_agent_definition_id, policy_key, semantic_version),
    KEY idx_ai_rag_policy_status (owner_agent_definition_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_agent_version_knowledge_binding (
    agent_version_id CHAR(36) NOT NULL,
    knowledge_base_id CHAR(36) NOT NULL,
    index_release_id CHAR(36) NOT NULL,
    priority INT NOT NULL,
    required TINYINT(1) NOT NULL,
    PRIMARY KEY (agent_version_id, knowledge_base_id),
    KEY idx_ai_agent_knowledge_release (index_release_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_agent_release (
    id CHAR(36) NOT NULL,
    agent_definition_id CHAR(36) NOT NULL,
    agent_version_id CHAR(36) NOT NULL,
    environment VARCHAR(32) NOT NULL,
    release_status VARCHAR(32) NOT NULL,
    release_snapshot_id CHAR(36) NULL,
    released_by VARCHAR(64) NOT NULL,
    released_at DATETIME(6) NULL,
    rolled_back_from_release_id CHAR(36) NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_ai_agent_release_env_status (agent_definition_id, environment, release_status),
    KEY idx_ai_agent_release_version (agent_version_id),
    KEY idx_ai_agent_release_rollback (rolled_back_from_release_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_agent_release_snapshot (
    id CHAR(36) NOT NULL,
    agent_release_id CHAR(36) NOT NULL,
    snapshot_json JSON NOT NULL,
    checksum CHAR(64) NOT NULL,
    agent_ack_status VARCHAR(32) NOT NULL,
    agent_ack_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_agent_release_snapshot_release (agent_release_id),
    UNIQUE KEY uk_ai_agent_release_snapshot_checksum (checksum)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_customer_service_conversation (
    id CHAR(36) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NULL,
    status VARCHAR(32) NOT NULL,
    last_agent_release_id CHAR(36) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_ai_cs_conversation_user_updated (tenant_id, user_id, updated_at),
    KEY idx_ai_cs_conversation_release (last_agent_release_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_customer_service_message (
    id CHAR(36) NOT NULL,
    conversation_id CHAR(36) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL,
    content_markdown LONGTEXT NOT NULL,
    answer_mode VARCHAR(32) NULL,
    run_id CHAR(36) NULL,
    client_request_id VARCHAR(128) NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_cs_message_request (tenant_id, client_request_id),
    KEY idx_ai_cs_message_conversation_created (conversation_id, created_at),
    KEY idx_ai_cs_message_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_customer_service_run (
    id CHAR(36) NOT NULL,
    conversation_id CHAR(36) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    user_message_id CHAR(36) NOT NULL,
    agent_run_id VARCHAR(128) NULL,
    agent_release_id CHAR(36) NOT NULL,
    status VARCHAR(32) NOT NULL,
    answer_mode VARCHAR(32) NULL,
    last_event_sequence BIGINT NOT NULL DEFAULT 0,
    failure_code VARCHAR(128) NULL,
    failure_message VARCHAR(1000) NULL,
    started_at DATETIME(6) NULL,
    finished_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_cs_run_agent (agent_run_id),
    KEY idx_ai_cs_run_conversation_created (conversation_id, created_at),
    KEY idx_ai_cs_run_status_updated (status, updated_at),
    KEY idx_ai_cs_run_release (agent_release_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_customer_service_run_step (
    id CHAR(36) NOT NULL,
    run_id CHAR(36) NOT NULL,
    sequence_no BIGINT NOT NULL,
    stage VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    public_summary VARCHAR(1000) NULL,
    internal_payload JSON NULL,
    started_at DATETIME(6) NULL,
    finished_at DATETIME(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_cs_run_step_sequence (run_id, sequence_no),
    KEY idx_ai_cs_run_step_stage (run_id, stage)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_customer_service_citation (
    id CHAR(36) NOT NULL,
    run_id CHAR(36) NOT NULL,
    message_id CHAR(36) NOT NULL,
    citation_no INT NOT NULL,
    knowledge_base_id CHAR(36) NOT NULL,
    document_id CHAR(36) NOT NULL,
    document_version_id CHAR(36) NOT NULL,
    index_release_id CHAR(36) NOT NULL,
    chunk_id CHAR(36) NOT NULL,
    document_title VARCHAR(500) NOT NULL,
    version_no INT NOT NULL,
    section_path VARCHAR(2000) NULL,
    page_no INT NULL,
    quoted_text TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_cs_citation_no (message_id, citation_no),
    KEY idx_ai_cs_citation_run (run_id),
    KEY idx_ai_cs_citation_document_version (document_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ai_customer_service_feedback (
    id CHAR(36) NOT NULL,
    conversation_id CHAR(36) NOT NULL,
    message_id CHAR(36) NOT NULL,
    run_id CHAR(36) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    rating VARCHAR(16) NOT NULL,
    reason_code VARCHAR(32) NULL,
    comment VARCHAR(1000) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_cs_feedback_user_message (tenant_id, user_id, message_id),
    KEY idx_ai_cs_feedback_run (run_id),
    KEY idx_ai_cs_feedback_rating_created (rating, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE sys_audit_log (
    id CHAR(36) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    actor_id VARCHAR(64) NOT NULL,
    action VARCHAR(128) NOT NULL,
    resource_type VARCHAR(128) NOT NULL,
    resource_id VARCHAR(128) NOT NULL,
    before_digest CHAR(64) NULL,
    after_digest CHAR(64) NULL,
    result VARCHAR(32) NOT NULL,
    trace_id VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_sys_audit_resource_created (resource_type, resource_id, created_at),
    KEY idx_sys_audit_actor_created (tenant_id, actor_id, created_at),
    KEY idx_sys_audit_trace (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
