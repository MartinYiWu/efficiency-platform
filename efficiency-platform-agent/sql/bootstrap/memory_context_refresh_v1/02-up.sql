-- RF02；前置 memory_execution_v1、memory_execution_scrub_v1、context_control_v1。
-- 必须停记忆流量；MySQL DDL 隐式提交，任何部分安装均保持停用，不能盲目重跑。
-- 仅授权执行器在专属随机隔离 schema 演练；共享库另行预检、授权与账本占用。
SET SESSION lock_wait_timeout=5;
SET SESSION innodb_lock_wait_timeout=5;
SET SESSION max_execution_time=10000;
ALTER TABLE agent_memory_execution
 ADD COLUMN current_context_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL;
-- 独立 DML 提交点；大表须按预检水位分批，本包仅允许已评审的小规模停写回填。
START TRANSACTION;
UPDATE agent_memory_execution SET current_context_fingerprint=context_fingerprint
 WHERE current_context_fingerprint IS NULL;
COMMIT;
ALTER TABLE agent_memory_execution
 MODIFY current_context_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 ADD CONSTRAINT ck_memory_execution_current_fp CHECK(REGEXP_LIKE(current_context_fingerprint,'^[0-9a-f]{64}$','c'));

CREATE TABLE agent_memory_context_refresh (
 tenant_id VARBINARY(512) NOT NULL,
 execution_id VARBINARY(512) NOT NULL,
 record_kind VARCHAR(8) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 record_id VARBINARY(512) NOT NULL,
 runtime_id VARBINARY(512) NOT NULL,
 task_id VARBINARY(512) NOT NULL,
 user_id VARBINARY(512) NOT NULL,
 domain VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 top_level_agent_id VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 session_kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 session_id VARBINARY(512) NULL,
 request_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 request_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 semantic_input_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 operation_id VARBINARY(512) NOT NULL,
 attempt INT UNSIGNED NOT NULL,
 canonical_request_hmac CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 stage_id VARBINARY(512) NULL,
 stage_slot INT UNSIGNED NULL,
 execution_revision BIGINT UNSIGNED NOT NULL,
 original_deadline BIGINT UNSIGNED NOT NULL,
 old_packet_revision BIGINT UNSIGNED NOT NULL,
 expected_current_context_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 wait_event_id VARBINARY(512) NULL,
 resume_request_id VARBINARY(512) NULL,
 wait_phase VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NULL,
 checkpoint_mode VARCHAR(8) CHARACTER SET ascii COLLATE ascii_bin NULL,
 checkpoint_ns VARBINARY(512) NULL,
 checkpoint_id VARBINARY(512) NULL,
 target_packet_revision BIGINT UNSIGNED NULL,
 target_context_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 target_snapshot_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 candidate_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 issued_at BIGINT UNSIGNED NULL,
 expires_at BIGINT UNSIGNED NULL,
 pg_ordinal INT UNSIGNED NULL,
 phase VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 candidate_phase VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NULL,
 next_wait_event_id VARBINARY(512) NULL,
 receipt_code VARCHAR(48) CHARACTER SET ascii COLLATE ascii_bin NULL,
 receipt_ref VARBINARY(512) NULL,
 receipt_state VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NULL,
 current_packet_revision BIGINT UNSIGNED NULL,
 current_context_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 refresh_count INT UNSIGNED NULL,
 dispatch_allowed BOOLEAN NOT NULL DEFAULT FALSE,
 resume_start VARCHAR(8) CHARACTER SET ascii COLLATE ascii_bin NULL,
 sent_packet_revision BIGINT UNSIGNED NULL,
 sent_packet_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 send_permit_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 result_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 body_ciphertext LONGBLOB NULL,
 body_nonce BINARY(12) NULL,
 key_version VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 body_scrub_event_id VARBINARY(512) NULL,
 open_wait_marker TINYINT GENERATED ALWAYS AS (CASE WHEN record_kind='WAIT' AND phase IN ('BUILDING','READY') THEN 1 ELSE NULL END) STORED,
 pending_marker TINYINT GENERATED ALWAYS AS (CASE WHEN record_kind='REFRESH' AND phase IN ('PENDING','SNAPSHOT_APPLIED') THEN 1 ELSE NULL END) STORED,
 result_operation_id VARBINARY(512) GENERATED ALWAYS AS (CASE WHEN record_kind='RESULT' THEN operation_id ELSE NULL END) STORED,
 result_attempt INT UNSIGNED GENERATED ALWAYS AS (CASE WHEN record_kind='RESULT' THEN attempt ELSE NULL END) STORED,
 PRIMARY KEY(tenant_id,execution_id,record_kind,record_id),
 UNIQUE KEY uk_memory_refresh_open_wait(tenant_id,execution_id,operation_id,attempt,old_packet_revision,open_wait_marker),
 UNIQUE KEY uk_memory_refresh_pending(tenant_id,execution_id,pending_marker),
 UNIQUE KEY uk_memory_refresh_result(tenant_id,execution_id,result_operation_id,result_attempt),
 CONSTRAINT fk_memory_refresh_execution FOREIGN KEY(tenant_id,execution_id) REFERENCES agent_memory_execution(tenant_id,execution_id),
 CONSTRAINT ck_memory_refresh_ids CHECK(OCTET_LENGTH(record_id)>0 AND OCTET_LENGTH(runtime_id)>0 AND OCTET_LENGTH(task_id)>0 AND OCTET_LENGTH(user_id)>0 AND OCTET_LENGTH(operation_id)>0),
 CONSTRAINT ck_memory_refresh_scope CHECK(domain IN ('operations','customer-service','hr') AND top_level_agent_id=domain AND ((session_kind='TASK_ONLY' AND session_id IS NULL) OR (session_kind='CONVERSATION' AND session_id IS NOT NULL AND OCTET_LENGTH(session_id)>0))),
 CONSTRAINT ck_memory_refresh_attempt CHECK(attempt BETWEEN 1 AND 3 AND execution_revision>0 AND original_deadline>0 AND old_packet_revision>0),
 CONSTRAINT ck_memory_refresh_hashes CHECK(REGEXP_LIKE(request_hash,'^[0-9a-f]{64}$','c') AND REGEXP_LIKE(request_fingerprint,'^[0-9a-f]{64}$','c') AND REGEXP_LIKE(semantic_input_hash,'^[0-9a-f]{64}$','c') AND REGEXP_LIKE(expected_current_context_fingerprint,'^[0-9a-f]{64}$','c') AND (canonical_request_hmac IS NULL OR REGEXP_LIKE(canonical_request_hmac,'^[0-9a-f]{64}$','c'))),
 CONSTRAINT ck_memory_refresh_stage CHECK((stage_id IS NULL AND stage_slot IS NULL) OR (stage_id IS NOT NULL AND OCTET_LENGTH(stage_id)>0 AND stage_slot IS NOT NULL AND stage_slot BETWEEN 1 AND 3)),
 CONSTRAINT ck_memory_refresh_body CHECK((body_ciphertext IS NOT NULL AND OCTET_LENGTH(body_ciphertext)>0 AND body_nonce IS NOT NULL AND body_scrub_event_id IS NULL) OR (body_ciphertext IS NULL AND body_nonce IS NULL AND body_scrub_event_id IS NOT NULL)),
 CONSTRAINT ck_memory_refresh_kind CHECK(
  (record_kind='WAIT' AND record_id=wait_event_id AND wait_event_id IS NOT NULL AND resume_request_id IS NULL AND wait_phase IS NOT NULL AND wait_phase IN ('BEFORE_PREPARE','PREPARED','RESERVED') AND checkpoint_mode IS NOT NULL AND checkpoint_mode IN ('GRAPH','NONE') AND phase IN ('BUILDING','READY','CONSUMED','SUPERSEDED','ABORTED') AND target_packet_revision IS NULL AND target_context_fingerprint IS NULL AND target_snapshot_hash IS NULL AND candidate_digest IS NULL AND issued_at IS NULL AND expires_at IS NULL AND pg_ordinal IS NULL AND candidate_phase IS NULL AND next_wait_event_id IS NULL AND sent_packet_revision IS NULL AND sent_packet_digest IS NULL AND send_permit_hash IS NULL AND result_hash IS NULL)
  OR (record_kind='REFRESH' AND record_id=resume_request_id AND resume_request_id IS NOT NULL AND wait_event_id IS NOT NULL AND wait_phase IS NOT NULL AND wait_phase IN ('BEFORE_PREPARE','PREPARED','RESERVED') AND checkpoint_mode IS NULL AND checkpoint_ns IS NULL AND checkpoint_id IS NULL AND phase IN ('PENDING','SNAPSHOT_APPLIED','ACKED','EXPIRED_UNAPPLIED','APPLIED_EXPIRED','ABORTED') AND target_packet_revision IS NOT NULL AND target_packet_revision>old_packet_revision AND target_context_fingerprint IS NOT NULL AND REGEXP_LIKE(target_context_fingerprint,'^[0-9a-f]{64}$','c') AND target_snapshot_hash IS NOT NULL AND REGEXP_LIKE(target_snapshot_hash,'^[0-9a-f]{64}$','c') AND candidate_digest IS NOT NULL AND REGEXP_LIKE(candidate_digest,'^[0-9a-f]{64}$','c') AND issued_at IS NOT NULL AND expires_at IS NOT NULL AND issued_at<expires_at AND expires_at<=original_deadline AND pg_ordinal IS NOT NULL AND pg_ordinal BETWEEN 1 AND 3 AND resume_start IS NULL AND sent_packet_revision IS NULL AND sent_packet_digest IS NULL AND send_permit_hash IS NULL AND result_hash IS NULL)
  OR (record_kind='RESULT' AND record_id=SHA2(CONCAT(OCTET_LENGTH(operation_id),':',operation_id,':',attempt),256) AND phase='CAPTURED' AND canonical_request_hmac IS NOT NULL AND wait_event_id IS NULL AND resume_request_id IS NULL AND wait_phase IS NULL AND checkpoint_mode IS NULL AND checkpoint_ns IS NULL AND checkpoint_id IS NULL AND target_packet_revision IS NULL AND target_context_fingerprint IS NULL AND target_snapshot_hash IS NULL AND candidate_digest IS NULL AND issued_at IS NULL AND expires_at IS NULL AND pg_ordinal IS NULL AND candidate_phase IS NULL AND next_wait_event_id IS NULL AND resume_start IS NULL AND sent_packet_revision IS NOT NULL AND sent_packet_revision>0 AND sent_packet_digest IS NOT NULL AND REGEXP_LIKE(sent_packet_digest,'^[0-9a-f]{64}$','c') AND send_permit_hash IS NOT NULL AND REGEXP_LIKE(send_permit_hash,'^[0-9a-f]{64}$','c') AND result_hash IS NOT NULL AND REGEXP_LIKE(result_hash,'^[0-9a-f]{64}$','c'))),
 CONSTRAINT ck_memory_refresh_hmac CHECK(record_kind='RESULT' OR (wait_phase='BEFORE_PREPARE' AND canonical_request_hmac IS NULL) OR (wait_phase IN ('PREPARED','RESERVED') AND canonical_request_hmac IS NOT NULL)),
 -- BUILDING 允许尚无实际 checkpoint；只有 READY/后继阶段才要求真实 id 的形状。真实性由 RF03 核 Saver/owned 登记。
 CONSTRAINT ck_memory_refresh_checkpoint CHECK(record_kind<>'WAIT' OR (checkpoint_mode='NONE' AND checkpoint_ns IS NULL AND checkpoint_id IS NULL) OR (checkpoint_mode='GRAPH' AND ((phase IN ('BUILDING','ABORTED') AND checkpoint_ns IS NULL AND checkpoint_id IS NULL) OR (phase<>'BUILDING' AND checkpoint_ns IS NOT NULL AND checkpoint_id IS NOT NULL AND OCTET_LENGTH(checkpoint_id)>0)))),
 CONSTRAINT ck_memory_refresh_resume_start CHECK(resume_start IS NULL OR (record_kind='WAIT' AND phase='CONSUMED' AND resume_start IN ('READY','CLAIMED','DONE'))),
 CONSTRAINT ck_memory_refresh_receipt_code CHECK(receipt_code IS NULL OR receipt_code IN ('CONTEXT_REFRESHED','CPU_CONFIRMED','MEMORY_REFRESH_PENDING','MEMORY_RESUME_CONFLICT','MEMORY_WAIT_CONSUMED','MEMORY_REVISION_CONFLICT','MEMORY_REFRESH_PACKET_EXPIRED','CONTEXT_REFRESH_LIMIT','EXECUTION_EXPIRED','SOURCE_CHANGED','SOURCE_REVOKED','ACCESS_REVOKED','CONTINUATION_AUTH_UNSUPPORTED','MEMORY_REFRESH_CAPABILITY_UNSUPPORTED','MEMORY_REFRESH_SCHEMA_REQUIRED','MEMORY_AUTHORITY_UNAVAILABLE','CONTEXT_INTERNAL_AUTH_REQUIRED','CONTEXT_SCOPE_MISMATCH','MEMORY_RESULT_UNAVAILABLE')),
 CONSTRAINT ck_memory_refresh_receipt CHECK(
  (record_kind<>'REFRESH' AND candidate_phase IS NULL AND receipt_code IS NULL AND receipt_ref IS NULL AND receipt_state IS NULL AND current_packet_revision IS NULL AND current_context_fingerprint IS NULL AND refresh_count IS NULL AND dispatch_allowed=FALSE)
  OR (record_kind='REFRESH' AND candidate_phase IS NOT NULL AND candidate_phase IN ('PENDING','ACKED','EXPIRED_UNAPPLIED','APPLIED_EXPIRED','ABORTED') AND receipt_code IS NOT NULL AND receipt_ref IS NOT NULL AND receipt_state IS NOT NULL AND receipt_state IN ('ACTIVE','WAITING_CONTEXT','REFRESH_PENDING','BLOCKED','EXPIRED','REVOKED','SCRUBBED','DELETED') AND current_packet_revision IS NOT NULL AND current_packet_revision>0 AND current_context_fingerprint IS NOT NULL AND REGEXP_LIKE(current_context_fingerprint,'^[0-9a-f]{64}$','c') AND refresh_count IS NOT NULL AND refresh_count BETWEEN 1 AND 3)),
 CONSTRAINT ck_memory_refresh_receipt_phase CHECK(record_kind<>'REFRESH' OR (phase IN ('PENDING','SNAPSHOT_APPLIED') AND candidate_phase='PENDING' AND receipt_code='MEMORY_REFRESH_PENDING' AND receipt_state='REFRESH_PENDING' AND dispatch_allowed=FALSE AND current_packet_revision=old_packet_revision AND current_context_fingerprint=expected_current_context_fingerprint) OR (phase='ACKED' AND candidate_phase='ACKED' AND receipt_code='CONTEXT_REFRESHED' AND receipt_state='ACTIVE' AND current_packet_revision=target_packet_revision AND current_context_fingerprint=target_context_fingerprint) OR (phase='EXPIRED_UNAPPLIED' AND candidate_phase='EXPIRED_UNAPPLIED' AND receipt_code='MEMORY_REFRESH_PACKET_EXPIRED' AND current_packet_revision=old_packet_revision AND current_context_fingerprint=expected_current_context_fingerprint AND next_wait_event_id IS NULL AND dispatch_allowed=FALSE AND ((refresh_count<3 AND receipt_state='WAITING_CONTEXT') OR (refresh_count=3 AND receipt_state='BLOCKED'))) OR (phase='APPLIED_EXPIRED' AND candidate_phase='APPLIED_EXPIRED' AND receipt_code='MEMORY_REFRESH_PACKET_EXPIRED' AND current_packet_revision=target_packet_revision AND current_context_fingerprint=target_context_fingerprint AND dispatch_allowed=FALSE AND ((refresh_count<3 AND receipt_state='WAITING_CONTEXT' AND next_wait_event_id IS NOT NULL) OR (receipt_state='BLOCKED' AND next_wait_event_id IS NULL))) OR (phase='ABORTED' AND candidate_phase='ABORTED' AND receipt_code NOT IN ('CPU_CONFIRMED','CONTINUATION_AUTH_UNSUPPORTED','CONTEXT_REFRESHED','MEMORY_REFRESH_PENDING','MEMORY_REFRESH_PACKET_EXPIRED') AND receipt_state IN ('BLOCKED','EXPIRED','REVOKED','SCRUBBED','DELETED') AND dispatch_allowed=FALSE)),
 CONSTRAINT ck_memory_refresh_ordinal CHECK(record_kind<>'REFRESH' OR refresh_count=pg_ordinal),
 CONSTRAINT ck_memory_refresh_next_wait CHECK(next_wait_event_id IS NULL OR (record_kind='REFRESH' AND phase='APPLIED_EXPIRED' AND next_wait_event_id<>wait_event_id AND receipt_state='WAITING_CONTEXT' AND refresh_count<3 AND dispatch_allowed=FALSE))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

DELIMITER $$
CREATE TRIGGER trg_memory_refresh_insert BEFORE INSERT ON agent_memory_context_refresh FOR EACH ROW
BEGIN
 DECLARE owner_count INT DEFAULT 0;
 DECLARE wait_count INT DEFAULT 0;
 SELECT COUNT(*) INTO owner_count FROM agent_memory_execution WHERE tenant_id=NEW.tenant_id AND execution_id=NEW.execution_id AND runtime_id=NEW.runtime_id AND state='ACTIVE' AND execution_revision=NEW.execution_revision AND original_deadline=NEW.original_deadline AND request_fingerprint=NEW.request_fingerprint AND current_context_fingerprint=NEW.expected_current_context_fingerprint AND key_version=NEW.key_version FOR UPDATE;
 IF owner_count<>1 OR NEW.body_ciphertext IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_OWNER_REQUIRED'; END IF;
 IF (NEW.record_kind='WAIT' AND NEW.phase<>'BUILDING') OR (NEW.record_kind='REFRESH' AND NEW.phase<>'PENDING') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_INITIAL_PHASE_REQUIRED'; END IF;
 IF NEW.record_kind='REFRESH' THEN
  SELECT COUNT(*) INTO wait_count FROM agent_memory_context_refresh WHERE tenant_id=NEW.tenant_id AND execution_id=NEW.execution_id AND record_kind='WAIT' AND record_id=NEW.wait_event_id AND phase='READY' AND body_ciphertext IS NOT NULL AND runtime_id=NEW.runtime_id AND task_id=NEW.task_id AND user_id=NEW.user_id AND domain=NEW.domain AND top_level_agent_id=NEW.top_level_agent_id AND session_kind=NEW.session_kind AND (session_id<=>NEW.session_id) AND operation_id=NEW.operation_id AND attempt=NEW.attempt AND (canonical_request_hmac<=>NEW.canonical_request_hmac) AND (stage_id<=>NEW.stage_id) AND (stage_slot<=>NEW.stage_slot) AND wait_phase=NEW.wait_phase AND old_packet_revision=NEW.old_packet_revision AND expected_current_context_fingerprint=NEW.expected_current_context_fingerprint LOCK IN SHARE MODE;
  IF wait_count<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_WAIT_REQUIRED'; END IF;
 END IF;
 IF NEW.record_kind='RESULT' THEN
  SELECT COUNT(*) INTO wait_count FROM agent_context_operation WHERE tenant_id=NEW.tenant_id AND task_id=NEW.task_id AND execution_id=NEW.execution_id AND operation_id=NEW.operation_id AND latest_attempt=NEW.attempt AND input_hash=NEW.canonical_request_hmac AND status IN ('SENT','UNKNOWN') FOR UPDATE;
  IF wait_count<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_RESULT_SENT_OPERATION_REQUIRED'; END IF;
 END IF;
END$$
CREATE TRIGGER trg_memory_refresh_update BEFORE UPDATE ON agent_memory_context_refresh FOR EACH ROW
BEGIN
 DECLARE proofs INT DEFAULT 0;
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.execution_id<=>OLD.execution_id) OR NOT(NEW.record_kind<=>OLD.record_kind) OR NOT(NEW.record_id<=>OLD.record_id) OR NOT(NEW.runtime_id<=>OLD.runtime_id) OR NOT(NEW.task_id<=>OLD.task_id) OR NOT(NEW.user_id<=>OLD.user_id) OR NOT(NEW.domain<=>OLD.domain) OR NOT(NEW.top_level_agent_id<=>OLD.top_level_agent_id) OR NOT(NEW.session_kind<=>OLD.session_kind) OR NOT(NEW.session_id<=>OLD.session_id) OR NOT(NEW.request_hash<=>OLD.request_hash) OR NOT(NEW.request_fingerprint<=>OLD.request_fingerprint) OR NOT(NEW.semantic_input_hash<=>OLD.semantic_input_hash) OR NOT(NEW.operation_id<=>OLD.operation_id) OR NOT(NEW.attempt<=>OLD.attempt) OR NOT(NEW.canonical_request_hmac<=>OLD.canonical_request_hmac) OR NOT(NEW.stage_id<=>OLD.stage_id) OR NOT(NEW.stage_slot<=>OLD.stage_slot) OR NOT(NEW.execution_revision<=>OLD.execution_revision) OR NOT(NEW.original_deadline<=>OLD.original_deadline) OR NOT(NEW.old_packet_revision<=>OLD.old_packet_revision) OR NOT(NEW.expected_current_context_fingerprint<=>OLD.expected_current_context_fingerprint) OR NOT(NEW.wait_event_id<=>OLD.wait_event_id) OR NOT(NEW.resume_request_id<=>OLD.resume_request_id) OR NOT(NEW.wait_phase<=>OLD.wait_phase) OR NOT(NEW.checkpoint_mode<=>OLD.checkpoint_mode) OR NOT(NEW.target_packet_revision<=>OLD.target_packet_revision) OR NOT(NEW.target_context_fingerprint<=>OLD.target_context_fingerprint) OR NOT(NEW.target_snapshot_hash<=>OLD.target_snapshot_hash) OR NOT(NEW.candidate_digest<=>OLD.candidate_digest) OR NOT(NEW.issued_at<=>OLD.issued_at) OR NOT(NEW.expires_at<=>OLD.expires_at) OR NOT(NEW.pg_ordinal<=>OLD.pg_ordinal) OR NOT(NEW.sent_packet_revision<=>OLD.sent_packet_revision) OR NOT(NEW.sent_packet_digest<=>OLD.sent_packet_digest) OR NOT(NEW.send_permit_hash<=>OLD.send_permit_hash) OR NOT(NEW.result_hash<=>OLD.result_hash) OR NOT(NEW.key_version<=>OLD.key_version) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_ANCHOR_IMMUTABLE'; END IF;
 IF OLD.body_ciphertext IS NULL AND NEW.body_ciphertext IS NOT NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_BODY_RESURRECTION'; END IF;
 IF NOT(NEW.body_ciphertext<=>OLD.body_ciphertext) OR NOT(NEW.body_nonce<=>OLD.body_nonce) OR NOT(NEW.body_scrub_event_id<=>OLD.body_scrub_event_id) THEN
  SELECT COUNT(*) INTO proofs FROM agent_memory_execution e JOIN agent_memory_invalidation_receipt r ON r.tenant_id=e.tenant_id AND r.execution_id=e.execution_id WHERE e.tenant_id=OLD.tenant_id AND e.execution_id=OLD.execution_id AND e.state='REVOKED' AND r.event_id=NEW.body_scrub_event_id AND r.expected_execution_revision=e.execution_revision AND r.grant_epoch=e.grant_epoch AND r.source_epoch=e.source_epoch AND r.deletion_epoch=e.deletion_epoch AND r.stop_confirmed=TRUE AND r.threads_receipt IS NOT NULL AND r.scrub_receipt IS NOT NULL AND r.cleanup_fingerprint IS NOT NULL FOR UPDATE;
  IF OLD.body_ciphertext IS NULL OR NEW.body_ciphertext IS NOT NULL OR NEW.body_nonce IS NOT NULL OR NEW.body_scrub_event_id IS NULL OR proofs<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_SCRUB_PROOF_REQUIRED'; END IF;
 END IF;
 IF NOT(NEW.next_wait_event_id<=>OLD.next_wait_event_id) AND OLD.next_wait_event_id IS NOT NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_NEXT_WAIT_IMMUTABLE'; END IF;
 IF NOT(NEW.checkpoint_ns<=>OLD.checkpoint_ns) OR NOT(NEW.checkpoint_id<=>OLD.checkpoint_id) THEN
  IF OLD.record_kind<>'WAIT' OR OLD.phase<>'BUILDING' OR NEW.phase<>'READY' OR OLD.checkpoint_id IS NOT NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_CHECKPOINT_IMMUTABLE'; END IF;
 END IF;
 IF NEW.phase<>OLD.phase AND NOT((OLD.record_kind='WAIT' AND ((OLD.phase='BUILDING' AND NEW.phase IN ('READY','ABORTED')) OR (OLD.phase='READY' AND NEW.phase IN ('CONSUMED','SUPERSEDED','ABORTED')))) OR (OLD.record_kind='REFRESH' AND ((OLD.phase='PENDING' AND NEW.phase IN ('SNAPSHOT_APPLIED','EXPIRED_UNAPPLIED','ABORTED')) OR (OLD.phase='SNAPSHOT_APPLIED' AND NEW.phase IN ('ACKED','APPLIED_EXPIRED','ABORTED'))))) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_PHASE_REGRESSION'; END IF;
 IF NOT(NEW.resume_start<=>OLD.resume_start) AND NOT((OLD.resume_start IS NULL AND (NEW.resume_start<=>'READY') AND NEW.record_kind='WAIT' AND NEW.phase='CONSUMED') OR ((OLD.resume_start<=>'READY') AND (NEW.resume_start<=>'CLAIMED')) OR ((OLD.resume_start<=>'CLAIMED') AND (NEW.resume_start<=>'DONE'))) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_RESUME_START_REGRESSION'; END IF;
 IF OLD.phase IN ('ACKED','EXPIRED_UNAPPLIED','APPLIED_EXPIRED','ABORTED','CAPTURED','SUPERSEDED') AND (NOT(NEW.candidate_phase<=>OLD.candidate_phase) OR NOT(NEW.next_wait_event_id<=>OLD.next_wait_event_id) OR NOT(NEW.receipt_code<=>OLD.receipt_code) OR NOT(NEW.receipt_ref<=>OLD.receipt_ref) OR NOT(NEW.receipt_state<=>OLD.receipt_state) OR NOT(NEW.current_packet_revision<=>OLD.current_packet_revision) OR NOT(NEW.current_context_fingerprint<=>OLD.current_context_fingerprint) OR NOT(NEW.refresh_count<=>OLD.refresh_count) OR NOT(NEW.dispatch_allowed<=>OLD.dispatch_allowed) OR NEW.phase<>OLD.phase) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_TERMINAL_IMMUTABLE'; END IF;
 IF OLD.body_ciphertext IS NULL AND (NEW.phase<>OLD.phase OR NOT(NEW.resume_start<=>OLD.resume_start) OR NOT(NEW.receipt_code<=>OLD.receipt_code) OR NOT(NEW.receipt_ref<=>OLD.receipt_ref) OR NOT(NEW.receipt_state<=>OLD.receipt_state) OR NOT(NEW.candidate_phase<=>OLD.candidate_phase) OR NOT(NEW.current_packet_revision<=>OLD.current_packet_revision) OR NOT(NEW.current_context_fingerprint<=>OLD.current_context_fingerprint) OR NOT(NEW.refresh_count<=>OLD.refresh_count) OR NOT(NEW.dispatch_allowed<=>OLD.dispatch_allowed) OR NOT(NEW.next_wait_event_id<=>OLD.next_wait_event_id)) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_SCRUBBED_IMMUTABLE'; END IF;
 IF NEW.phase<>OLD.phase AND NEW.phase<>'ABORTED' THEN
  SELECT COUNT(*) INTO proofs FROM agent_memory_execution WHERE tenant_id=NEW.tenant_id AND execution_id=NEW.execution_id AND state='ACTIVE' FOR UPDATE;
  IF proofs<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_ACTIVE_REQUIRED'; END IF;
 END IF;
 IF NEW.record_kind='REFRESH' AND NEW.phase<>OLD.phase AND NEW.phase IN ('SNAPSHOT_APPLIED','ACKED','APPLIED_EXPIRED','EXPIRED_UNAPPLIED') THEN
  SELECT COUNT(*) INTO proofs FROM agent_memory_execution WHERE tenant_id=NEW.tenant_id AND execution_id=NEW.execution_id AND state='ACTIVE' AND ((NEW.phase='EXPIRED_UNAPPLIED' AND current_context_fingerprint=NEW.expected_current_context_fingerprint) OR (NEW.phase<>'EXPIRED_UNAPPLIED' AND current_context_fingerprint=NEW.target_context_fingerprint AND SHA2(CONCAT(snapshot_nonce,snapshot_ciphertext),256)=NEW.target_snapshot_hash)) FOR UPDATE;
  IF proofs<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_LOCAL_APPLICATION_REQUIRED'; END IF;
 END IF;
 IF NEW.next_wait_event_id IS NOT NULL AND OLD.next_wait_event_id IS NULL THEN
  SELECT COUNT(*) INTO proofs FROM agent_memory_context_refresh WHERE tenant_id=NEW.tenant_id AND execution_id=NEW.execution_id AND record_kind='WAIT' AND record_id=NEW.next_wait_event_id AND phase='READY' AND body_ciphertext IS NOT NULL AND runtime_id=NEW.runtime_id AND task_id=NEW.task_id AND operation_id=NEW.operation_id AND attempt=NEW.attempt AND (canonical_request_hmac<=>NEW.canonical_request_hmac) AND (stage_id<=>NEW.stage_id) AND (stage_slot<=>NEW.stage_slot) AND wait_phase=NEW.wait_phase AND old_packet_revision=NEW.target_packet_revision AND expected_current_context_fingerprint=NEW.target_context_fingerprint LOCK IN SHARE MODE;
  IF proofs<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_NEXT_WAIT_REQUIRED'; END IF;
 END IF;
END$$
CREATE TRIGGER trg_memory_refresh_delete BEFORE DELETE ON agent_memory_context_refresh FOR EACH ROW
BEGIN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_DELETE_FORBIDDEN';
END$$
CREATE TRIGGER trg_memory_execution_refresh BEFORE UPDATE ON agent_memory_execution FOR EACH ROW FOLLOWS trg_memory_execution_scrub
BEGIN
 DECLARE matches INT DEFAULT 0;
 IF NOT(NEW.current_context_fingerprint<=>OLD.current_context_fingerprint) OR NOT(NEW.snapshot_ciphertext<=>OLD.snapshot_ciphertext) OR NOT(NEW.snapshot_nonce<=>OLD.snapshot_nonce) THEN
  -- 旧 scrub trigger 仍核完整证明；新分支只允许正文清空且 current 指纹不动。
  IF OLD.state='REVOKED' AND NEW.state='SCRUBBED' AND NEW.snapshot_ciphertext IS NULL AND NEW.snapshot_nonce IS NULL AND (NEW.current_context_fingerprint<=>OLD.current_context_fingerprint) THEN
   SELECT COUNT(*) INTO matches FROM agent_memory_context_refresh WHERE tenant_id=OLD.tenant_id AND execution_id=OLD.execution_id AND body_ciphertext IS NOT NULL;
   IF matches<>0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_BODIES_NOT_SCRUBBED'; END IF;
  ELSE
   IF OLD.state<>'ACTIVE' OR NEW.state<>'ACTIVE' OR NOT(NEW.grant_epoch<=>OLD.grant_epoch) OR NOT(NEW.source_epoch<=>OLD.source_epoch) OR NOT(NEW.deletion_epoch<=>OLD.deletion_epoch) OR (NEW.current_context_fingerprint<=>OLD.current_context_fingerprint) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_JOURNAL_REQUIRED'; END IF;
   SELECT COUNT(*) INTO matches FROM agent_memory_context_refresh r JOIN agent_memory_context_refresh w ON w.tenant_id=r.tenant_id AND w.execution_id=r.execution_id AND w.record_kind='WAIT' AND w.record_id=r.wait_event_id WHERE r.tenant_id=OLD.tenant_id AND r.execution_id=OLD.execution_id AND r.record_kind='REFRESH' AND r.phase='PENDING' AND r.runtime_id=OLD.runtime_id AND r.request_fingerprint=OLD.request_fingerprint AND r.execution_revision=OLD.execution_revision AND r.original_deadline=OLD.original_deadline AND r.key_version=OLD.key_version AND r.expected_current_context_fingerprint=OLD.current_context_fingerprint AND r.target_context_fingerprint=NEW.current_context_fingerprint AND r.target_snapshot_hash=SHA2(CONCAT(NEW.snapshot_nonce,NEW.snapshot_ciphertext),256) AND r.body_ciphertext IS NOT NULL AND w.phase='READY' AND w.body_ciphertext IS NOT NULL AND w.expected_current_context_fingerprint=OLD.current_context_fingerprint AND w.old_packet_revision=r.old_packet_revision FOR UPDATE;
   IF matches<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_JOURNAL_REQUIRED'; END IF;
  END IF;
 END IF;
END$$
DELIMITER ;
