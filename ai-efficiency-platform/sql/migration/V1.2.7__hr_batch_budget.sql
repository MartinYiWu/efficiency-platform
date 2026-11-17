-- 批次不可变预算引用，仅新增本表，由root统一执行。
CREATE TABLE ai_hr_batch_budget (
 tenant_id VARCHAR(64) NOT NULL,batch_id VARCHAR(64) NOT NULL,department_id VARCHAR(64) NOT NULL,
 payload LONGTEXT NOT NULL, PRIMARY KEY(tenant_id,batch_id), KEY idx_hr_batch_budget_scope(tenant_id,department_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
