-- aiep-biz-aihub RF02；只新增 ai_memory_packet_refresh，不覆盖 V1.2.17 或原 packet。
-- 前置 verification/V1.2.18__precheck_memory_context_refresh.sql；仅独立评审后获授权执行。
-- 原会话、原期限与来源下限仅在首次签包短事务写 ANCHOR；旧 execution 不补新会话。
-- MySQL DDL 隐式提交；无历史回填。回滚见 rollback/R__V1.2.18__memory_context_refresh.sql，仅未使用允许。
SET SESSION lock_wait_timeout=5;
SET SESSION innodb_lock_wait_timeout=5;
SET SESSION max_execution_time=10000;
CREATE TABLE ai_memory_packet_refresh (
 tenant_id VARBINARY(512) NOT NULL,
 execution_id VARBINARY(512) NOT NULL,
 record_kind VARCHAR(8) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 record_id VARBINARY(512) NOT NULL,
 user_id VARBINARY(512) NOT NULL,
 packet_id VARBINARY(512) NOT NULL,
 initial_packet_revision BIGINT UNSIGNED NOT NULL,
 execution_revision BIGINT UNSIGNED NOT NULL,
 request_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 semantic_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 original_deadline BIGINT UNSIGNED NOT NULL,
 original_session_ref VARBINARY(512) NULL,
 policy_ttl_seconds INT UNSIGNED NOT NULL,
 source_retention_deadline BIGINT UNSIGNED NOT NULL,
 resume_request_id VARBINARY(512) NULL,
 wait_event_id VARBINARY(512) NULL,
 old_packet_revision BIGINT UNSIGNED NULL,
 target_revision BIGINT UNSIGNED NULL,
 expected_current_context_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 request_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 candidate_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 issued_at BIGINT UNSIGNED NULL,
 expires_at BIGINT UNSIGNED NULL,
 phase VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 receipt_code VARCHAR(48) CHARACTER SET ascii COLLATE ascii_bin NULL,
 receipt_ref VARBINARY(512) NULL,
 candidate_phase VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NULL,
 current_packet_revision BIGINT UNSIGNED NULL,
 current_context_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 refresh_count INT UNSIGNED NULL,
 receipt_state VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NULL,
 next_wait_event_id VARBINARY(512) NULL,
 dispatch_allowed BOOLEAN NOT NULL DEFAULT FALSE,
 anchor_marker TINYINT GENERATED ALWAYS AS (CASE WHEN record_kind='ANCHOR' THEN 1 ELSE NULL END) STORED,
 PRIMARY KEY(tenant_id,execution_id,record_kind,record_id),
 UNIQUE KEY uk_memory_packet_refresh_anchor(tenant_id,execution_id,anchor_marker),
 UNIQUE KEY uk_memory_packet_refresh_request(tenant_id,execution_id,record_kind,resume_request_id),
 UNIQUE KEY uk_memory_packet_refresh_revision(tenant_id,packet_id,target_revision),
 CONSTRAINT fk_memory_packet_refresh_execution FOREIGN KEY(tenant_id,execution_id) REFERENCES ai_memory_packet(tenant_id,execution_id),
 CONSTRAINT ck_memory_packet_refresh_ids CHECK(OCTET_LENGTH(record_id)>0 AND OCTET_LENGTH(user_id)>0 AND OCTET_LENGTH(packet_id)>0),
 CONSTRAINT ck_memory_packet_refresh_anchors CHECK(initial_packet_revision>0 AND execution_revision>0 AND original_deadline>0 AND policy_ttl_seconds BETWEEN 1 AND 60 AND source_retention_deadline>0 AND REGEXP_LIKE(request_digest,'^[0-9a-f]{64}$','c') AND REGEXP_LIKE(semantic_digest,'^[0-9a-f]{64}$','c')),
 CONSTRAINT ck_memory_packet_refresh_kind CHECK(
  (record_kind='ANCHOR' AND record_id=execution_id AND phase='ANCHORED' AND original_session_ref IS NOT NULL AND OCTET_LENGTH(original_session_ref)>0 AND resume_request_id IS NULL AND wait_event_id IS NULL AND old_packet_revision IS NULL AND target_revision IS NULL AND expected_current_context_fingerprint IS NULL AND request_hash IS NULL AND candidate_digest IS NULL AND issued_at IS NULL AND expires_at IS NULL)
  OR (record_kind='REFRESH' AND record_id=resume_request_id AND resume_request_id IS NOT NULL AND OCTET_LENGTH(resume_request_id)>0 AND original_session_ref IS NULL AND wait_event_id IS NOT NULL AND OCTET_LENGTH(wait_event_id)>0 AND old_packet_revision IS NOT NULL AND old_packet_revision>=initial_packet_revision AND target_revision IS NOT NULL AND target_revision>old_packet_revision AND expected_current_context_fingerprint IS NOT NULL AND REGEXP_LIKE(expected_current_context_fingerprint,'^[0-9a-f]{64}$','c') AND request_hash IS NOT NULL AND REGEXP_LIKE(request_hash,'^[0-9a-f]{64}$','c') AND candidate_digest IS NOT NULL AND REGEXP_LIKE(candidate_digest,'^[0-9a-f]{64}$','c') AND issued_at IS NOT NULL AND expires_at IS NOT NULL AND issued_at<expires_at AND expires_at<=original_deadline AND expires_at<=source_retention_deadline AND expires_at-issued_at<=policy_ttl_seconds AND phase IN ('PREPARED','ACKED','EXPIRED_UNAPPLIED','APPLIED_EXPIRED','ABORTED'))),
 CONSTRAINT ck_memory_packet_refresh_code CHECK(receipt_code IS NULL OR receipt_code IN ('CONTEXT_REFRESHED','CPU_CONFIRMED','MEMORY_REFRESH_PENDING','MEMORY_RESUME_CONFLICT','MEMORY_WAIT_CONSUMED','MEMORY_REVISION_CONFLICT','MEMORY_REFRESH_PACKET_EXPIRED','CONTEXT_REFRESH_LIMIT','EXECUTION_EXPIRED','SOURCE_CHANGED','SOURCE_REVOKED','ACCESS_REVOKED','CONTINUATION_AUTH_UNSUPPORTED','MEMORY_REFRESH_CAPABILITY_UNSUPPORTED','MEMORY_REFRESH_SCHEMA_REQUIRED','MEMORY_AUTHORITY_UNAVAILABLE','CONTEXT_INTERNAL_AUTH_REQUIRED','CONTEXT_SCOPE_MISMATCH','MEMORY_RESULT_UNAVAILABLE')),
 CONSTRAINT ck_memory_packet_refresh_receipt CHECK(
  (phase IN ('ANCHORED','PREPARED') AND receipt_code IS NULL AND receipt_ref IS NULL AND candidate_phase IS NULL AND current_packet_revision IS NULL AND current_context_fingerprint IS NULL AND refresh_count IS NULL AND receipt_state IS NULL AND next_wait_event_id IS NULL AND dispatch_allowed=FALSE)
  OR (record_kind='REFRESH' AND phase NOT IN ('ANCHORED','PREPARED') AND receipt_code IS NOT NULL AND receipt_ref IS NOT NULL AND candidate_phase IS NOT NULL AND candidate_phase=phase AND current_packet_revision IS NOT NULL AND current_packet_revision>0 AND current_context_fingerprint IS NOT NULL AND REGEXP_LIKE(current_context_fingerprint,'^[0-9a-f]{64}$','c') AND refresh_count IS NOT NULL AND refresh_count BETWEEN 1 AND 3 AND receipt_state IS NOT NULL AND receipt_state IN ('ACTIVE','WAITING_CONTEXT','REFRESH_PENDING','BLOCKED','EXPIRED','REVOKED','SCRUBBED','DELETED'))),
 CONSTRAINT ck_memory_packet_refresh_phase CHECK(phase IN ('ANCHORED','PREPARED')
  OR (phase='ACKED' AND receipt_code='CONTEXT_REFRESHED' AND receipt_state='ACTIVE' AND current_packet_revision=target_revision AND next_wait_event_id IS NULL)
  OR (phase='EXPIRED_UNAPPLIED' AND receipt_code='MEMORY_REFRESH_PACKET_EXPIRED' AND current_packet_revision=old_packet_revision AND current_context_fingerprint=expected_current_context_fingerprint AND next_wait_event_id IS NULL AND dispatch_allowed=FALSE AND ((refresh_count<3 AND receipt_state='WAITING_CONTEXT') OR (refresh_count=3 AND receipt_state='BLOCKED')))
  OR (phase='APPLIED_EXPIRED' AND receipt_code='MEMORY_REFRESH_PACKET_EXPIRED' AND current_packet_revision=target_revision AND dispatch_allowed=FALSE AND ((refresh_count<3 AND receipt_state='WAITING_CONTEXT' AND next_wait_event_id IS NOT NULL AND next_wait_event_id<>wait_event_id) OR (receipt_state='BLOCKED' AND next_wait_event_id IS NULL)))
  OR (phase='ABORTED' AND receipt_code NOT IN ('CPU_CONFIRMED','CONTINUATION_AUTH_UNSUPPORTED','CONTEXT_REFRESHED','MEMORY_REFRESH_PENDING','MEMORY_REFRESH_PACKET_EXPIRED') AND receipt_state IN ('BLOCKED','EXPIRED','REVOKED','SCRUBBED','DELETED') AND dispatch_allowed=FALSE AND next_wait_event_id IS NULL))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

DELIMITER $$
CREATE TRIGGER trg_memory_packet_refresh_insert BEFORE INSERT ON ai_memory_packet_refresh FOR EACH ROW
BEGIN
 DECLARE matches INT DEFAULT 0;
 DECLARE candidates INT DEFAULT 0;
 DECLARE unresolved INT DEFAULT 0;
 DECLARE highest_revision BIGINT UNSIGNED DEFAULT 0;
 SELECT COUNT(*) INTO matches FROM ai_memory_packet WHERE tenant_id=NEW.tenant_id AND execution_id=NEW.execution_id AND user_id=NEW.user_id AND packet_id=NEW.packet_id AND packet_revision=NEW.initial_packet_revision AND execution_revision=NEW.execution_revision AND request_digest=NEW.request_digest AND semantic_digest=NEW.semantic_digest AND original_deadline=NEW.original_deadline FOR UPDATE;
 IF matches<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_PACKET_ANCHOR_REQUIRED'; END IF;
 IF NEW.record_kind='REFRESH' THEN
  SELECT COUNT(*) INTO matches FROM ai_memory_packet_refresh WHERE tenant_id=NEW.tenant_id AND execution_id=NEW.execution_id AND record_kind='ANCHOR' AND user_id=NEW.user_id AND packet_id=NEW.packet_id AND initial_packet_revision=NEW.initial_packet_revision AND execution_revision=NEW.execution_revision AND request_digest=NEW.request_digest AND semantic_digest=NEW.semantic_digest AND original_deadline=NEW.original_deadline AND policy_ttl_seconds=NEW.policy_ttl_seconds AND source_retention_deadline=NEW.source_retention_deadline LOCK IN SHARE MODE;
  IF matches<>1 OR NEW.phase<>'PREPARED' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_ANCHOR_REQUIRED'; END IF;
  SELECT COUNT(*) INTO candidates FROM ai_memory_packet_refresh WHERE tenant_id=NEW.tenant_id AND execution_id=NEW.execution_id AND record_kind='REFRESH' AND wait_event_id=NEW.wait_event_id LOCK IN SHARE MODE;
  IF candidates>=3 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_CANDIDATE_LIMIT'; END IF;
  SELECT COUNT(*) INTO unresolved FROM ai_memory_packet_refresh WHERE tenant_id=NEW.tenant_id AND execution_id=NEW.execution_id AND record_kind='REFRESH' AND phase='PREPARED' LOCK IN SHARE MODE;
  SELECT COALESCE(MAX(target_revision),NEW.initial_packet_revision) INTO highest_revision FROM ai_memory_packet_refresh WHERE tenant_id=NEW.tenant_id AND execution_id=NEW.execution_id AND record_kind='REFRESH' LOCK IN SHARE MODE;
  IF NEW.target_revision<=highest_revision THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_REVISION_REGRESSION'; END IF;
  IF unresolved<>0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_PREPARED_PENDING'; END IF;
 END IF;
END$$
CREATE TRIGGER trg_memory_packet_refresh_update BEFORE UPDATE ON ai_memory_packet_refresh FOR EACH ROW
BEGIN
 IF OLD.record_kind='ANCHOR' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_ANCHOR_IMMUTABLE'; END IF;
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.execution_id<=>OLD.execution_id) OR NOT(NEW.record_kind<=>OLD.record_kind) OR NOT(NEW.record_id<=>OLD.record_id) OR NOT(NEW.user_id<=>OLD.user_id) OR NOT(NEW.packet_id<=>OLD.packet_id) OR NOT(NEW.initial_packet_revision<=>OLD.initial_packet_revision) OR NOT(NEW.execution_revision<=>OLD.execution_revision) OR NOT(NEW.request_digest<=>OLD.request_digest) OR NOT(NEW.semantic_digest<=>OLD.semantic_digest) OR NOT(NEW.original_deadline<=>OLD.original_deadline) OR NOT(NEW.original_session_ref<=>OLD.original_session_ref) OR NOT(NEW.policy_ttl_seconds<=>OLD.policy_ttl_seconds) OR NOT(NEW.source_retention_deadline<=>OLD.source_retention_deadline) OR NOT(NEW.resume_request_id<=>OLD.resume_request_id) OR NOT(NEW.wait_event_id<=>OLD.wait_event_id) OR NOT(NEW.old_packet_revision<=>OLD.old_packet_revision) OR NOT(NEW.target_revision<=>OLD.target_revision) OR NOT(NEW.expected_current_context_fingerprint<=>OLD.expected_current_context_fingerprint) OR NOT(NEW.request_hash<=>OLD.request_hash) OR NOT(NEW.candidate_digest<=>OLD.candidate_digest) OR NOT(NEW.issued_at<=>OLD.issued_at) OR NOT(NEW.expires_at<=>OLD.expires_at) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_ANCHOR_IMMUTABLE'; END IF;
 IF OLD.phase<>'PREPARED' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_TERMINAL_IMMUTABLE';
 END IF;
 IF NEW.phase NOT IN ('ACKED','EXPIRED_UNAPPLIED','APPLIED_EXPIRED','ABORTED') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_PHASE_REGRESSION'; END IF;
END$$
CREATE TRIGGER trg_memory_packet_refresh_delete BEFORE DELETE ON ai_memory_packet_refresh FOR EACH ROW
BEGIN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_DELETE_FORBIDDEN';
END$$
DELIMITER ;
