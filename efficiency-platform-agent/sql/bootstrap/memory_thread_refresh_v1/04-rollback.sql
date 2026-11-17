-- 单一事务硬拒绝已使用增量及墓碑；不清零旧计数、不删除旧 RESUME/ERASURE 回执。
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
LOCK TABLE agent_memory_thread_execution,agent_memory_thread_resume IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM agent_memory_thread_resume WHERE record_kind IS NOT NULL)
 OR EXISTS(SELECT 1 FROM agent_memory_thread_execution WHERE current_context_fingerprint IS NOT NULL OR wait_status IS NOT NULL OR pending_resume_request_id IS NOT NULL OR terminal_reason IS NOT NULL OR state IN ('WAITING_CONTEXT','REFRESH_PENDING','REVOKED','SCRUBBED','DELETED')) THEN
  RAISE EXCEPTION 'MEMORY_REFRESH_ROLLBACK_REQUIRES_UNUSED';
 END IF;
END $$;
DROP TRIGGER trg_memory_thread_refresh_execution ON agent_memory_thread_execution;
DROP TRIGGER trg_memory_thread_refresh_receipt ON agent_memory_thread_resume;
DROP FUNCTION memory_thread_refresh_execution_guard();
DROP FUNCTION memory_thread_refresh_receipt_guard();
DROP INDEX uk_memory_thread_refresh_pending;
DROP INDEX uk_memory_thread_refresh_candidate;
ALTER TABLE agent_memory_thread_execution DROP CONSTRAINT ck_memory_thread_refresh_state,DROP CONSTRAINT ck_memory_thread_current_fp,DROP CONSTRAINT ck_memory_thread_wait,DROP CONSTRAINT ck_memory_thread_pending,
 DROP COLUMN current_context_fingerprint,
 DROP COLUMN wait_status,
 DROP COLUMN wait_packet_revision,
 DROP COLUMN wait_context_fingerprint,
 DROP COLUMN wait_phase,
 DROP COLUMN wait_checkpoint_ns,
 DROP COLUMN wait_checkpoint_id,
 DROP COLUMN pending_resume_request_id,
 DROP COLUMN pending_candidate_digest,
 DROP COLUMN pending_packet_revision,
 DROP COLUMN pending_context_fingerprint,
 DROP COLUMN terminal_reason,
 ADD CONSTRAINT agent_memory_thread_execution_state_check CHECK(state IN ('ACTIVE','BLOCKED','REVOKED','DELETED','EXPIRED'));
ALTER TABLE agent_memory_thread_resume DROP CONSTRAINT ck_memory_thread_resume_shape,DROP CONSTRAINT ck_memory_thread_resume_code,DROP CONSTRAINT ck_memory_thread_resume_legacy_code,DROP CONSTRAINT ck_memory_thread_resume_key,DROP CONSTRAINT ck_memory_thread_resume_phase,
 DROP COLUMN record_kind,
 DROP COLUMN candidate_id,
 DROP COLUMN wait_event_id,
 DROP COLUMN operation_id,
 DROP COLUMN attempt,
 DROP COLUMN canonical_request_hmac,
 DROP COLUMN wait_phase,
 DROP COLUMN old_packet_revision,
 DROP COLUMN packet_revision,
 DROP COLUMN execution_revision,
 DROP COLUMN expected_current_context_fingerprint,
 DROP COLUMN target_context_fingerprint,
 DROP COLUMN candidate_digest,
 DROP COLUMN issued_at,
 DROP COLUMN expires_at,
 DROP COLUMN candidate_phase,
 DROP COLUMN current_packet_revision,
 DROP COLUMN current_context_fingerprint,
 DROP COLUMN refresh_count,
 DROP COLUMN receipt_state,
 DROP COLUMN next_wait_event_id,
 DROP COLUMN dispatch_allowed,
 DROP COLUMN authorization_binding;
COMMIT;
