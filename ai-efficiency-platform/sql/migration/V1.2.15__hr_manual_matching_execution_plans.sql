-- 显式手工匹配固定业务scope与不可变预算；不复活原上传批次执行。
CREATE TABLE ai_hr_matching_execution_plan (
 tenant_id VARCHAR(64) NOT NULL,scope_ref VARCHAR(100) NOT NULL,run_id VARCHAR(64) NOT NULL,payload LONGTEXT NOT NULL,
 PRIMARY KEY(tenant_id,scope_ref),UNIQUE KEY uk_hr_manual_matching_run(tenant_id,run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
