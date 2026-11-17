-- 任务9/10：新增HR拥有的持久对象；个人正文仍由AES-GCM加密。
CREATE TABLE ai_hr_candidate_merge (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, primary_candidate_id CHAR(36) NOT NULL,
 source_ids LONGTEXT NOT NULL, status VARCHAR(24) NOT NULL, created_at TIMESTAMP(6) NOT NULL,
 revocable_until TIMESTAMP(6) NOT NULL, version BIGINT NOT NULL, created_by VARCHAR(64) NOT NULL,
 PRIMARY KEY(id), KEY ix_hr_merge_primary(tenant_id,primary_candidate_id,status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_candidate_source (
 tenant_id VARCHAR(64) NOT NULL, source_candidate_id CHAR(36) NOT NULL, merge_id CHAR(36) NOT NULL,
 primary_candidate_id CHAR(36) NOT NULL, status VARCHAR(24) NOT NULL,
 PRIMARY KEY(tenant_id,source_candidate_id), KEY ix_hr_source_merge(tenant_id,merge_id,status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_interview_set (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, candidate_id CHAR(36) NOT NULL,
 position_id CHAR(36) NOT NULL, version BIGINT NOT NULL, status VARCHAR(32) NOT NULL,
 payload LONGTEXT NOT NULL, provenance LONGTEXT NOT NULL, cache_key CHAR(64) NOT NULL,
 created_by VARCHAR(64) NOT NULL, created_at TIMESTAMP(6) NOT NULL,
 PRIMARY KEY(tenant_id,id,version), KEY ix_hr_interview_candidate(tenant_id,candidate_id,created_at),
 KEY ix_hr_interview_cache(tenant_id,cache_key,status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_interview_assignment (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, set_id CHAR(36) NOT NULL,
 set_version BIGINT NOT NULL, interviewer_id VARCHAR(64) NOT NULL, expires_at TIMESTAMP(6) NOT NULL,
 status VARCHAR(24) NOT NULL, created_by VARCHAR(64) NOT NULL,
 PRIMARY KEY(id), KEY ix_hr_assignment_user(tenant_id,interviewer_id,status,expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_contact_grant (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, candidate_id CHAR(36) NOT NULL,
 user_id VARCHAR(64) NOT NULL, expires_at TIMESTAMP(6) NOT NULL, status VARCHAR(24) NOT NULL,
 PRIMARY KEY(id), KEY ix_hr_contact_candidate(tenant_id,candidate_id,status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_deletion_job (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, candidate_id CHAR(36) NOT NULL,
 department_id VARCHAR(64) NOT NULL, status VARCHAR(24) NOT NULL, step VARCHAR(24) NOT NULL,
 attempts INT NOT NULL, next_attempt_at TIMESTAMP(6) NOT NULL, created_at TIMESTAMP(6) NOT NULL,
 failure_code VARCHAR(100) NULL, PRIMARY KEY(id), KEY ix_hr_deletion_due(status,next_attempt_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_audit (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, action VARCHAR(64) NOT NULL,
 actor_id VARCHAR(64) NOT NULL, subject_ref CHAR(64) NOT NULL, department_id VARCHAR(64) NOT NULL,
 occurred_at TIMESTAMP(6) NOT NULL, PRIMARY KEY(id), KEY ix_hr_audit_scope(tenant_id,department_id,occurred_at,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_interview_export (
 id CHAR(36) NOT NULL, tenant_id VARCHAR(64) NOT NULL, set_id CHAR(36) NOT NULL,
 set_version BIGINT NOT NULL, user_id VARCHAR(64) NOT NULL, assignment_id CHAR(36) NULL,
 format VARCHAR(16) NOT NULL, payload LONGTEXT NOT NULL, grant_id CHAR(36) NOT NULL,
 expires_at TIMESTAMP(6) NOT NULL, status VARCHAR(24) NOT NULL, PRIMARY KEY(id),
 UNIQUE KEY uk_hr_download_grant(grant_id), KEY ix_hr_export_set(tenant_id,set_id,status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_talent_operation (
 tenant_id VARCHAR(64) NOT NULL, actor_id VARCHAR(64) NOT NULL, route VARCHAR(100) NOT NULL,
 idempotency_key VARCHAR(100) NOT NULL, request_hash CHAR(64) NOT NULL, result_ref VARCHAR(100) NOT NULL,
 PRIMARY KEY(tenant_id,actor_id,route,idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
