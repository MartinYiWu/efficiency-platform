-- 先停写且人工确认以下为0；存在SCRUBBED时拒绝回滚，不能恢复已擦正文。
SELECT COUNT(*) AS rollback_blocking_scrubbed FROM agent_memory_execution WHERE state='SCRUBBED';
-- ALTER本身会对SCRUBBED/null行失败；先验证再移除保护trigger。
ALTER TABLE agent_memory_execution DROP CHECK ck_memory_execution_body, DROP CHECK ck_memory_execution_state,
 MODIFY snapshot_ciphertext LONGBLOB NOT NULL, MODIFY snapshot_nonce BINARY(12) NOT NULL,
 ADD CONSTRAINT ck_memory_execution_state CHECK(state IN ('ACTIVE','REVOKED')),
 DROP COLUMN scrub_event_id,DROP COLUMN scrub_authority;
DROP TRIGGER trg_memory_execution_scrub;
ALTER TABLE agent_memory_invalidation_receipt DROP COLUMN cleanup_fingerprint,DROP COLUMN stop_confirmed,DROP COLUMN threads_receipt,DROP COLUMN scrub_receipt,DROP COLUMN expected_execution_revision,DROP COLUMN grant_epoch,DROP COLUMN source_epoch,DROP COLUMN deletion_epoch;
