-- 批量面试/导出独立持久状态，刷新只读，重启不重发收费。
CREATE TABLE ai_hr_interview_batch (
 id CHAR(36) NOT NULL,tenant_id VARCHAR(64) NOT NULL,actor_id VARCHAR(64) NOT NULL,kind VARCHAR(24) NOT NULL,
 status VARCHAR(24) NOT NULL,payload LONGTEXT NOT NULL,input_json LONGTEXT NOT NULL,idempotency_key VARCHAR(100) NOT NULL,input_hash CHAR(64) NOT NULL,
 PRIMARY KEY(id),UNIQUE KEY uk_hr_interview_batch(tenant_id,actor_id,kind,idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
