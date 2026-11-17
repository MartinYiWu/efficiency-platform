-- 人事首闭环：仅新增aihub拥有表；不修改既有业务数据，不建立跨模块物理外键。
CREATE TABLE ai_hr_position_sequence (
 tenant_id VARCHAR(64) NOT NULL, department_id VARCHAR(64) NOT NULL, next_value BIGINT NOT NULL,
 PRIMARY KEY(tenant_id,department_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ai_hr_position (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, name VARCHAR(160) NOT NULL,
 normalized_name VARCHAR(160) NOT NULL, family VARCHAR(32) NOT NULL, department_id VARCHAR(64) NOT NULL,
 level VARCHAR(32) NOT NULL, code VARCHAR(96) NOT NULL, status VARCHAR(24) NOT NULL,
 config_version VARCHAR(32) NULL, context_version VARCHAR(64) NOT NULL,
 created_by VARCHAR(64) NOT NULL, created_at TIMESTAMP(6) NOT NULL, version BIGINT NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_hr_position_name(tenant_id,department_id,normalized_name),
 UNIQUE KEY uk_hr_position_code(tenant_id,code), KEY ix_hr_position_scope(tenant_id,department_id,created_at,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ai_hr_position_draft (
 tenant_id VARCHAR(64) NOT NULL, position_id CHAR(36) NOT NULL, payload LONGTEXT NOT NULL, version BIGINT NOT NULL,
 PRIMARY KEY(tenant_id,position_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ai_hr_config_version (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, position_id CHAR(36) NOT NULL,
 config_version VARCHAR(32) NOT NULL, payload LONGTEXT NOT NULL, snapshot_hash CHAR(64) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_hr_config_version(tenant_id,position_id,config_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ai_hr_candidate (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, department_id VARCHAR(64) NOT NULL,
 current_snapshot_id CHAR(36) NOT NULL, version BIGINT NOT NULL,
 consent_policy_id CHAR(36) NULL, acquired_at TIMESTAMP(6) NULL, expires_at TIMESTAMP(6) NULL,
 status VARCHAR(24) NOT NULL DEFAULT 'ACTIVE',
 PRIMARY KEY(id), KEY ix_hr_candidate_scope(tenant_id,department_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- facts_json/结果及判断快照均由AES-GCM封装，LONGTEXT不代表可存明文简历。
CREATE TABLE ai_hr_fact_snapshot (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, candidate_id CHAR(36) NOT NULL,
 resume_version_id CHAR(36) NOT NULL, version BIGINT NOT NULL, facts_json LONGTEXT NOT NULL,
 created_by VARCHAR(64) NOT NULL, created_at TIMESTAMP(6) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_hr_fact_version(tenant_id,candidate_id,version),
 KEY ix_hr_fact_resume(tenant_id,resume_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ai_hr_semantic_snapshot (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, candidate_id CHAR(36) NOT NULL,
 fact_snapshot_id CHAR(36) NOT NULL, config_json LONGTEXT NOT NULL,
 assessments_json LONGTEXT NOT NULL, hard_conditions_json LONGTEXT NOT NULL, created_at TIMESTAMP(6) NOT NULL,
 PRIMARY KEY(id), KEY ix_hr_semantic_source(tenant_id,candidate_id,fact_snapshot_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ai_hr_matching_run (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, candidate_id CHAR(36) NOT NULL,
 position_id CHAR(36) NOT NULL, status VARCHAR(32) NOT NULL, result_id CHAR(36) NULL,
 failure_code VARCHAR(100) NULL, created_at TIMESTAMP(6) NOT NULL,
 input_json LONGTEXT NOT NULL, deadline_at TIMESTAMP(6) NOT NULL,
 idempotency_key VARCHAR(100) NOT NULL, request_hash CHAR(64) NOT NULL, scope_ref VARCHAR(100) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_hr_run_idempotency(tenant_id,idempotency_key), KEY ix_hr_run_candidate(tenant_id,candidate_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ai_hr_matching_result (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, candidate_id CHAR(36) NOT NULL,
 position_id CHAR(36) NOT NULL, fact_snapshot_id CHAR(36) NOT NULL,
 config_version VARCHAR(32) NOT NULL, context_version VARCHAR(64) NOT NULL,
 semantic_snapshot_id CHAR(36) NULL, result_json LONGTEXT NOT NULL,
 status VARCHAR(32) NOT NULL, business_status VARCHAR(32) NOT NULL, superseded_by CHAR(36) NULL, created_at TIMESTAMP(6) NOT NULL,
 PRIMARY KEY(id), KEY ix_hr_result_scope(tenant_id,position_id,config_version,status,created_at,id),
 KEY ix_hr_result_candidate(tenant_id,candidate_id,fact_snapshot_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ai_hr_policy_version (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, payload LONGTEXT NOT NULL,
 version BIGINT NOT NULL, created_at TIMESTAMP(6) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_hr_policy_version(tenant_id,version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ai_hr_batch (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, department_id VARCHAR(64) NOT NULL,
 user_id VARCHAR(64) NOT NULL, position_id CHAR(36) NULL, mode VARCHAR(24) NOT NULL,
 policy_id CHAR(36) NOT NULL, maximum_items INT NOT NULL, status VARCHAR(32) NOT NULL,
 version BIGINT NOT NULL, created_at TIMESTAMP(6) NOT NULL, idempotency_key VARCHAR(100) NOT NULL,
 request_hash CHAR(64) NOT NULL, PRIMARY KEY(id), UNIQUE KEY uk_hr_batch_key(tenant_id,idempotency_key),
 KEY ix_hr_batch_scope(tenant_id,department_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ai_hr_batch_item (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, batch_id CHAR(36) NOT NULL,
 filename VARCHAR(255) NOT NULL, encrypted_content LONGTEXT NULL, content_hash CHAR(64) NOT NULL,
 status VARCHAR(32) NOT NULL, stage VARCHAR(32) NULL, candidate_id CHAR(36) NULL,
 error_code VARCHAR(100) NULL, progress INT NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_hr_batch_hash(tenant_id,batch_id,content_hash),
 KEY ix_hr_batch_items(tenant_id,batch_id,status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
