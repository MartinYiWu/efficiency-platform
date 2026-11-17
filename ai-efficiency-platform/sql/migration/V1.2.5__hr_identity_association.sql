-- 来源身份检索仅保存租户HMAC，不存联系人明文；关联仍保留每个来源授权。
CREATE TABLE ai_hr_identity_signal (
 tenant_id VARCHAR(64) NOT NULL,candidate_id CHAR(36) NOT NULL,kind VARCHAR(16) NOT NULL,
 signal_key CHAR(64) NOT NULL,quality INT NOT NULL,shared_contact TINYINT NOT NULL,conflict_contact TINYINT NOT NULL,
 PRIMARY KEY(tenant_id,candidate_id,kind,signal_key),KEY ix_hr_identity_lookup(tenant_id,kind,signal_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_identity_association (
 id CHAR(36) NOT NULL,tenant_id VARCHAR(64) NOT NULL,primary_candidate_id CHAR(36) NOT NULL,
 source_candidate_id CHAR(36) NOT NULL,resume_version_id CHAR(36) NOT NULL,
 status VARCHAR(24) NOT NULL,created_at TIMESTAMP(6) NOT NULL,
 PRIMARY KEY(id),UNIQUE KEY uk_hr_identity_source_version(tenant_id,source_candidate_id,resume_version_id,primary_candidate_id),
 KEY ix_hr_identity_primary(tenant_id,primary_candidate_id,status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
