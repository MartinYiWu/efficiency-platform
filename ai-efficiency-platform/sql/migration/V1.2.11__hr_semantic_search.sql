-- 语义检索任务仅保存加密冻结请求/结果，GET不生成。
CREATE TABLE ai_hr_semantic_search_job (
 id CHAR(36) NOT NULL,tenant_id VARCHAR(64) NOT NULL,actor_id VARCHAR(64) NOT NULL,
 status VARCHAR(32) NOT NULL,input_json LONGTEXT NOT NULL,result_json LONGTEXT NOT NULL,
 idempotency_key VARCHAR(100) NOT NULL,request_hash CHAR(64) NOT NULL,
 created_at TIMESTAMP(6) NOT NULL,updated_at TIMESTAMP(6) NOT NULL,
 PRIMARY KEY(id),UNIQUE KEY uk_hr_search_key(tenant_id,actor_id,idempotency_key),
 KEY ix_hr_search_owner(tenant_id,actor_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_semantic_search_source (
 tenant_id VARCHAR(64) NOT NULL,job_id CHAR(36) NOT NULL,candidate_id CHAR(36) NOT NULL,
 PRIMARY KEY(tenant_id,job_id,candidate_id),KEY ix_hr_search_source(tenant_id,candidate_id,job_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
