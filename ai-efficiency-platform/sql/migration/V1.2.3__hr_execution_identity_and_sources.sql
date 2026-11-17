-- HR续闭环运行、来源授权与身份接合；仅新增表，不覆盖V1.2.0数据。
CREATE TABLE id_hr_session (
 credential_hash CHAR(64) NOT NULL,tenant_id VARCHAR(64) NOT NULL,user_id VARCHAR(64) NOT NULL,
 expires_at TIMESTAMP(6) NOT NULL,revoked_at TIMESTAMP(6) NULL,PRIMARY KEY(credential_hash),KEY ix_id_hr_session(tenant_id,user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE id_hr_grant (
 id CHAR(36) NOT NULL,tenant_id VARCHAR(64) NOT NULL,user_id VARCHAR(64) NOT NULL,
 department_id VARCHAR(64) NULL,permission VARCHAR(100) NOT NULL,position_id VARCHAR(64) NULL,candidate_id VARCHAR(64) NULL,
 revoked_at TIMESTAMP(6) NULL,PRIMARY KEY(id),KEY ix_id_hr_grant(tenant_id,user_id,revoked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_source_authorization (
 tenant_id VARCHAR(64) NOT NULL,candidate_id CHAR(36) NOT NULL,policy_id CHAR(36) NOT NULL,purposes VARCHAR(100) NOT NULL,
 identity_json LONGTEXT NOT NULL,extraction_json LONGTEXT NOT NULL,file_id CHAR(36) NULL,wait_until TIMESTAMP(6) NOT NULL,
 continuation_state VARCHAR(32) NOT NULL,PRIMARY KEY(tenant_id,candidate_id),KEY ix_hr_source_wait(continuation_state,wait_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_feedback (
 id CHAR(36) NOT NULL,tenant_id VARCHAR(64) NOT NULL,result_id CHAR(36) NOT NULL,rating VARCHAR(24) NOT NULL,
 reason_json TEXT NOT NULL,actor_id VARCHAR(64) NOT NULL,created_at TIMESTAMP(6) NOT NULL,
 PRIMARY KEY(id),KEY ix_hr_feedback_result(tenant_id,result_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_run_event (
 tenant_id VARCHAR(64) NOT NULL,run_id CHAR(36) NOT NULL,sequence BIGINT NOT NULL,status VARCHAR(32) NOT NULL,
 result_id CHAR(36) NULL,failure_code VARCHAR(100) NULL,created_at TIMESTAMP(6) NOT NULL,
 PRIMARY KEY(tenant_id,run_id,sequence)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_context_version (
 tenant_id VARCHAR(64) NOT NULL,position_id CHAR(36) NOT NULL,context_version VARCHAR(64) NOT NULL,
 payload LONGTEXT NOT NULL,snapshot_hash CHAR(64) NOT NULL,created_at TIMESTAMP(6) NOT NULL,created_by VARCHAR(64) NOT NULL,
 PRIMARY KEY(tenant_id,position_id,context_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_batch_limits (
 tenant_id VARCHAR(64) NOT NULL,batch_id CHAR(36) NOT NULL,limits_json TEXT NOT NULL,PRIMARY KEY(tenant_id,batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE pf_private_file (
 id CHAR(36) NOT NULL,tenant_id VARCHAR(64) NOT NULL,hash CHAR(64) NOT NULL,size_bytes BIGINT NOT NULL,
 filename VARCHAR(255) NOT NULL,object_path VARCHAR(100) NOT NULL,status VARCHAR(24) NOT NULL,
 PRIMARY KEY(id),KEY ix_private_hash(tenant_id,hash,status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE pf_private_reference (
 tenant_id VARCHAR(64) NOT NULL,source_ref VARCHAR(100) NOT NULL,file_id CHAR(36) NOT NULL,
 PRIMARY KEY(tenant_id,source_ref,file_id),KEY ix_private_refs(tenant_id,file_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
