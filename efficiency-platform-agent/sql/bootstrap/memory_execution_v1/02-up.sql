-- D13技术表；仅在明确授权的Agent自有Schema执行，不由应用启动自动运行。
CREATE TABLE agent_memory_execution (
 tenant_id VARBINARY(512) NOT NULL,
 execution_id VARBINARY(512) NOT NULL,
 runtime_id VARBINARY(512) NOT NULL,
 runtime_kind VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 request_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 context_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 snapshot_ciphertext LONGBLOB NOT NULL,
 snapshot_nonce BINARY(12) NOT NULL,
 key_version VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 original_deadline BIGINT UNSIGNED NOT NULL,
 execution_revision BIGINT UNSIGNED NOT NULL,
 grant_epoch BIGINT UNSIGNED NOT NULL,
 source_epoch BIGINT UNSIGNED NOT NULL,
 deletion_epoch BIGINT UNSIGNED NOT NULL,
 state VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 PRIMARY KEY(tenant_id,execution_id),
 UNIQUE KEY uk_memory_runtime(tenant_id,runtime_kind,runtime_id),
 CONSTRAINT ck_memory_execution_state CHECK(state IN ('ACTIVE','REVOKED')),
 CONSTRAINT ck_memory_execution_kind CHECK(runtime_kind IN ('OPERATIONS','CUSTOMER_SERVICE','HR')),
 CONSTRAINT ck_memory_execution_deadline CHECK(original_deadline > 0),
 CONSTRAINT ck_memory_execution_revision CHECK(execution_revision > 0)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE agent_memory_invalidation_receipt (
 tenant_id VARBINARY(512) NOT NULL,
 event_id VARBINARY(512) NOT NULL,
 execution_id VARBINARY(512) NOT NULL,
 event_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 receipt_ref VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 PRIMARY KEY(tenant_id,event_id),
 CONSTRAINT fk_memory_invalidation_execution FOREIGN KEY(tenant_id,execution_id)
   REFERENCES agent_memory_execution(tenant_id,execution_id)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
