CREATE TABLE agent_model_policy (
    id BIGINT NOT NULL AUTO_INCREMENT,
    policy_key VARCHAR(128) NOT NULL,
    semantic_version VARCHAR(32) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    model_name VARCHAR(128) NOT NULL,
    temperature DECIMAL(5,4) NOT NULL,
    top_p DECIMAL(5,4) NULL,
    max_input_tokens INT NOT NULL,
    max_output_tokens INT NOT NULL,
    connect_timeout_ms INT NOT NULL,
    read_timeout_ms INT NOT NULL,
    max_retries INT NOT NULL,
    max_tool_calls INT NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    checksum CHAR(64) NOT NULL,
    created_at_epoch_ms BIGINT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_model_policy_key_version (policy_key, semantic_version),
    KEY idx_agent_model_policy_enabled (enabled, policy_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE agent_output_contract (
    id BIGINT NOT NULL AUTO_INCREMENT,
    contract_key VARCHAR(128) NOT NULL,
    semantic_version VARCHAR(32) NOT NULL,
    json_schema JSON NOT NULL,
    field_description LONGTEXT NOT NULL,
    checksum CHAR(64) NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_at_epoch_ms BIGINT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_output_contract_key_version (contract_key, semantic_version),
    KEY idx_agent_output_contract_enabled (enabled, contract_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE agent_prompt_definition (
    id BIGINT NOT NULL AUTO_INCREMENT,
    prompt_key VARCHAR(128) NOT NULL,
    scenario VARCHAR(64) NOT NULL,
    stage_key VARCHAR(64) NOT NULL,
    platform VARCHAR(64) NULL,
    name VARCHAR(255) NOT NULL,
    description VARCHAR(1000) NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_at_epoch_ms BIGINT NOT NULL,
    updated_at_epoch_ms BIGINT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_prompt_definition_key (prompt_key),
    KEY idx_agent_prompt_definition_route (scenario, stage_key, platform, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE agent_prompt_version (
    id BIGINT NOT NULL AUTO_INCREMENT,
    prompt_definition_id BIGINT NOT NULL,
    semantic_version VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    model_policy_id BIGINT NOT NULL,
    output_contract_id BIGINT NOT NULL,
    checksum CHAR(64) NOT NULL,
    change_summary VARCHAR(1000) NOT NULL,
    created_by VARCHAR(128) NOT NULL,
    created_at_epoch_ms BIGINT NOT NULL,
    released_at_epoch_ms BIGINT NULL,
    supersedes_version_id BIGINT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_prompt_version_semver (prompt_definition_id, semantic_version),
    UNIQUE KEY uk_agent_prompt_version_identity (id, prompt_definition_id),
    KEY idx_agent_prompt_version_status (prompt_definition_id, status),
    CONSTRAINT fk_prompt_version_definition FOREIGN KEY (prompt_definition_id)
        REFERENCES agent_prompt_definition (id),
    CONSTRAINT fk_prompt_version_model_policy FOREIGN KEY (model_policy_id)
        REFERENCES agent_model_policy (id),
    CONSTRAINT fk_prompt_version_output_contract FOREIGN KEY (output_contract_id)
        REFERENCES agent_output_contract (id),
    CONSTRAINT fk_prompt_version_supersedes FOREIGN KEY (supersedes_version_id)
        REFERENCES agent_prompt_version (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE agent_prompt_message_template (
    id BIGINT NOT NULL AUTO_INCREMENT,
    prompt_version_id BIGINT NOT NULL,
    ordinal INT NOT NULL,
    role VARCHAR(32) NOT NULL,
    message_key VARCHAR(128) NOT NULL,
    content_template LONGTEXT NOT NULL,
    content_format VARCHAR(16) NOT NULL,
    trusted_instruction TINYINT(1) NOT NULL,
    checksum CHAR(64) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_prompt_message_ordinal (prompt_version_id, ordinal),
    UNIQUE KEY uk_prompt_message_key (prompt_version_id, message_key),
    CONSTRAINT fk_prompt_message_version FOREIGN KEY (prompt_version_id)
        REFERENCES agent_prompt_version (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE agent_prompt_variable (
    id BIGINT NOT NULL AUTO_INCREMENT,
    prompt_message_template_id BIGINT NOT NULL,
    variable_name VARCHAR(128) NOT NULL,
    value_type VARCHAR(32) NOT NULL,
    value_source VARCHAR(32) NOT NULL,
    required TINYINT(1) NOT NULL,
    sensitive TINYINT(1) NOT NULL,
    max_length INT NOT NULL,
    allow_untrusted_content TINYINT(1) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_prompt_variable_name (
        prompt_message_template_id, variable_name
    ),
    CONSTRAINT fk_prompt_variable_message FOREIGN KEY (prompt_message_template_id)
        REFERENCES agent_prompt_message_template (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE agent_prompt_release (
    id BIGINT NOT NULL AUTO_INCREMENT,
    environment VARCHAR(32) NOT NULL,
    prompt_definition_id BIGINT NOT NULL,
    prompt_version_id BIGINT NOT NULL,
    released_by VARCHAR(128) NOT NULL,
    released_at_epoch_ms BIGINT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_prompt_release_active (environment, prompt_definition_id),
    KEY idx_agent_prompt_release_version (prompt_version_id),
    CONSTRAINT fk_prompt_release_definition FOREIGN KEY (prompt_definition_id)
        REFERENCES agent_prompt_definition (id),
    CONSTRAINT fk_prompt_release_version_definition FOREIGN KEY (
        prompt_version_id, prompt_definition_id
    ) REFERENCES agent_prompt_version (id, prompt_definition_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE agent_run_prompt_snapshot (
    id BIGINT NOT NULL AUTO_INCREMENT,
    run_id VARCHAR(128) NOT NULL,
    stage_key VARCHAR(128) NOT NULL,
    prompt_definition_id BIGINT NOT NULL,
    prompt_version_id BIGINT NOT NULL,
    model_policy_id BIGINT NOT NULL,
    output_contract_id BIGINT NOT NULL,
    message_checksum CHAR(64) NOT NULL,
    rendered_messages_checksum CHAR(64) NOT NULL,
    variable_values_checksum CHAR(64) NOT NULL,
    referenced_snapshot_json JSON NOT NULL,
    created_at_epoch_ms BIGINT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_run_prompt_snapshot_stage (run_id, stage_key),
    KEY idx_agent_run_prompt_snapshot_version (prompt_version_id),
    CONSTRAINT fk_run_prompt_snapshot_run FOREIGN KEY (run_id)
        REFERENCES agent_run (run_id),
    CONSTRAINT fk_run_prompt_snapshot_prompt FOREIGN KEY (
        prompt_version_id, prompt_definition_id
    ) REFERENCES agent_prompt_version (id, prompt_definition_id),
    CONSTRAINT fk_run_prompt_snapshot_model FOREIGN KEY (model_policy_id)
        REFERENCES agent_model_policy (id),
    CONSTRAINT fk_run_prompt_snapshot_contract FOREIGN KEY (output_contract_id)
        REFERENCES agent_output_contract (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE agent_prompt_test_case (
    id BIGINT NOT NULL AUTO_INCREMENT,
    prompt_version_id BIGINT NOT NULL,
    case_key VARCHAR(128) NOT NULL,
    input_json JSON NOT NULL,
    expected_contract_key VARCHAR(128) NOT NULL,
    forbidden_fields_json JSON NOT NULL,
    reviewer_note VARCHAR(2000) NULL,
    created_at_epoch_ms BIGINT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_prompt_test_case_key (prompt_version_id, case_key),
    CONSTRAINT fk_prompt_test_case_version FOREIGN KEY (prompt_version_id)
        REFERENCES agent_prompt_version (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
