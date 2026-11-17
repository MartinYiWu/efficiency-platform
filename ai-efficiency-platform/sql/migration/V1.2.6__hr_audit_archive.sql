-- 审计冷归档：仅保存不可逆墓碑及无正文事件，不提供业务写入API。
CREATE TABLE ai_hr_audit_archive (
 id CHAR(36) NOT NULL,tenant_id VARCHAR(64) NOT NULL,action VARCHAR(64) NOT NULL,
 actor_id VARCHAR(64) NOT NULL,subject_ref CHAR(64) NOT NULL,department_id VARCHAR(64) NOT NULL,
 occurred_at TIMESTAMP(6) NOT NULL,archived_at TIMESTAMP(6) NOT NULL,
 PRIMARY KEY(id),KEY ix_hr_audit_archive_retention(occurred_at,tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
