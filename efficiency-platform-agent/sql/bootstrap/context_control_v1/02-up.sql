-- 预检确认无同名表且获得明确 DDL 授权后执行；不包含实际 Prompt。
CREATE TABLE agent_context_operation (
 tenant_id VARBINARY(512) NOT NULL,
 task_id VARBINARY(512) NOT NULL,
 execution_id VARBINARY(512) NOT NULL,
 operation_id VARBINARY(512) NOT NULL,
 input_hash CHAR(64) COLLATE ascii_bin NOT NULL,
 status VARCHAR(16) COLLATE ascii_bin NOT NULL,
 deadline BIGINT UNSIGNED NOT NULL,
 latest_attempt INT UNSIGNED NOT NULL,
 receipt_ref VARCHAR(128) NULL,
 PRIMARY KEY(tenant_id,task_id,execution_id,operation_id),
 KEY ix_context_operation_status (tenant_id,status,deadline),
 CONSTRAINT ck_context_operation_attempt CHECK(latest_attempt BETWEEN 1 AND 3),
 CONSTRAINT ck_context_operation_status CHECK(status IN ('NOT_SENT','SENT','UNKNOWN','SUCCEEDED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE agent_context_manifest (
 tenant_id VARBINARY(512) NOT NULL,
 task_id VARBINARY(512) NOT NULL,
 execution_id VARBINARY(512) NOT NULL,
 operation_id VARBINARY(512) NOT NULL,
 attempt INT UNSIGNED NOT NULL,
 input_hash CHAR(64) COLLATE ascii_bin NOT NULL,
 metadata_json JSON NOT NULL,
 PRIMARY KEY(tenant_id,task_id,execution_id,operation_id,attempt),
 CONSTRAINT fk_context_manifest_operation FOREIGN KEY(tenant_id,task_id,execution_id,operation_id) REFERENCES agent_context_operation(tenant_id,task_id,execution_id,operation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
