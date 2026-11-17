-- 面试生成冻结岗位配置，不在编辑/单题再生时偷换成最新岗位规则。
CREATE TABLE ai_hr_interview_generation (
 tenant_id VARCHAR(64) NOT NULL,set_id CHAR(36) NOT NULL,config_json LONGTEXT NOT NULL,
 provenance LONGTEXT NOT NULL,PRIMARY KEY(tenant_id,set_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
