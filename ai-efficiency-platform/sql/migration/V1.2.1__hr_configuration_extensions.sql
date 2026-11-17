-- HR配置扩展；只新增配置文档/不可变版本/无正文审计。由负责人统一授权执行。
CREATE TABLE ai_hr_configuration_document (
 tenant_id VARCHAR(64) NOT NULL, kind VARCHAR(40) NOT NULL, id VARCHAR(64) NOT NULL,
 department_id VARCHAR(64) NOT NULL, payload LONGTEXT NOT NULL, version BIGINT NOT NULL,
 PRIMARY KEY (tenant_id,kind,id), KEY idx_hr_cfg_scope (tenant_id,kind,department_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_configuration_version (
 id VARCHAR(64) NOT NULL, tenant_id VARCHAR(64) NOT NULL, kind VARCHAR(40) NOT NULL,
 object_id VARCHAR(64) NOT NULL, payload LONGTEXT NOT NULL, version BIGINT NOT NULL, created_at DATETIME(6) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_hr_cfg_version(tenant_id,kind,object_id,version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE ai_hr_configuration_audit (
 id VARCHAR(64) NOT NULL, tenant_id VARCHAR(64) NOT NULL, department_id VARCHAR(64) NOT NULL,
 kind VARCHAR(40) NOT NULL, object_id VARCHAR(64) NOT NULL, action VARCHAR(40) NOT NULL,
 actor_id VARCHAR(64) NOT NULL, version BIGINT NOT NULL, created_at DATETIME(6) NOT NULL,
 PRIMARY KEY(id), KEY idx_hr_cfg_audit_scope(tenant_id,department_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
