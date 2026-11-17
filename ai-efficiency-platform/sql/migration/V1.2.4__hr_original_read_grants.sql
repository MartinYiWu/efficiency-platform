-- 原件访问一次性grant；不授予候选人或附件读取权，读取时仍核验当前授权。
CREATE TABLE ai_hr_original_grant (
 id CHAR(36) NOT NULL,tenant_id VARCHAR(64) NOT NULL,candidate_id CHAR(36) NOT NULL,user_id VARCHAR(64) NOT NULL,
 expires_at TIMESTAMP(6) NOT NULL,status VARCHAR(24) NOT NULL,PRIMARY KEY(id),KEY ix_hr_original_candidate(tenant_id,candidate_id,status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
