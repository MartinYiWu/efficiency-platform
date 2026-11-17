-- 仅在明确授权的Agent自有MySQL库预检后执行；不新增费用额度。
CREATE TABLE agent_context_stage (
 tenant_id VARBINARY(512) NOT NULL,
 task_id VARBINARY(512) NOT NULL,
 execution_id VARBINARY(512) NOT NULL,
 stage_id VARBINARY(512) NOT NULL,
 scope_hash CHAR(64) COLLATE ascii_bin NOT NULL,
 semantic_hash VARCHAR(128) COLLATE ascii_bin NOT NULL,
 deadline BIGINT UNSIGNED NOT NULL,
 current_slot INT UNSIGNED NOT NULL,
 status VARCHAR(16) COLLATE ascii_bin NOT NULL,
 operation_id_1 VARCHAR(128) COLLATE ascii_bin NOT NULL,
 operation_id_2 VARCHAR(128) COLLATE ascii_bin NOT NULL,
 operation_id_3 VARCHAR(128) COLLATE ascii_bin NOT NULL,
 PRIMARY KEY(tenant_id,task_id,execution_id,stage_id),
 KEY ix_context_stage_status (tenant_id,status,deadline),
 CONSTRAINT ck_context_stage_slot CHECK(current_slot BETWEEN 1 AND 3),
 CONSTRAINT ck_context_stage_status CHECK(status IN ('CLAIMED','RETURNED','SUCCEEDED','INVALID','UNKNOWN')),
 CONSTRAINT ck_context_stage_distinct_operations CHECK(operation_id_1<>operation_id_2 AND operation_id_1<>operation_id_3 AND operation_id_2<>operation_id_3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
