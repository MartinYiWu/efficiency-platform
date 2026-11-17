-- RF02；保留旧 counter、RESUME/ERASURE 回执与 capability_v1。仅显式授权的独立 schema。
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE agent_memory_thread_execution
 DROP CONSTRAINT agent_memory_thread_execution_state_check,
 ADD COLUMN current_context_fingerprint text,
 ADD COLUMN wait_status text,
 ADD COLUMN wait_packet_revision bigint,
 ADD COLUMN wait_context_fingerprint text,
 ADD COLUMN wait_phase text,
 ADD COLUMN wait_checkpoint_ns text,
 ADD COLUMN wait_checkpoint_id text,
 ADD COLUMN pending_resume_request_id text,
 ADD COLUMN pending_candidate_digest text,
 ADD COLUMN pending_packet_revision bigint,
 ADD COLUMN pending_context_fingerprint text,
 ADD COLUMN terminal_reason text,
 ADD CONSTRAINT ck_memory_thread_refresh_state CHECK(state IN ('ACTIVE','WAITING_CONTEXT','REFRESH_PENDING','BLOCKED','REVOKED','SCRUBBED','DELETED','EXPIRED')),
 ADD CONSTRAINT ck_memory_thread_current_fp CHECK(current_context_fingerprint IS NULL OR current_context_fingerprint ~ '^[0-9a-f]{64}$'),
 ADD CONSTRAINT ck_memory_thread_wait CHECK(
  (wait_status IS NULL AND wait_packet_revision IS NULL AND wait_context_fingerprint IS NULL AND wait_phase IS NULL AND wait_checkpoint_ns IS NULL AND wait_checkpoint_id IS NULL AND state NOT IN ('WAITING_CONTEXT','REFRESH_PENDING'))
  OR (wait_status IS NOT NULL AND wait_status IN ('BUILDING','READY') AND wait_event_id IS NOT NULL AND length(wait_event_id)>0 AND wait_packet_revision IS NOT NULL AND wait_packet_revision>0 AND wait_context_fingerprint IS NOT NULL AND wait_context_fingerprint ~ '^[0-9a-f]{64}$' AND wait_phase IS NOT NULL AND wait_phase IN ('BEFORE_PREPARE','PREPARED','RESERVED') AND current_context_fingerprint IS NOT NULL AND ((checkpoint_mode='NONE' AND wait_checkpoint_ns IS NULL AND wait_checkpoint_id IS NULL) OR (checkpoint_mode='GRAPH' AND ((wait_status='BUILDING' AND wait_checkpoint_ns IS NULL AND wait_checkpoint_id IS NULL) OR (wait_status='READY' AND wait_checkpoint_ns IS NOT NULL AND wait_checkpoint_id IS NOT NULL AND length(wait_checkpoint_id)>0)))) AND state IN ('WAITING_CONTEXT','REFRESH_PENDING','BLOCKED','REVOKED','SCRUBBED','DELETED','EXPIRED'))),
 ADD CONSTRAINT ck_memory_thread_pending CHECK(
  (state='REFRESH_PENDING' AND wait_status='READY' AND pending_resume_request_id IS NOT NULL AND length(pending_resume_request_id)>0 AND pending_candidate_digest IS NOT NULL AND pending_candidate_digest ~ '^[0-9a-f]{64}$' AND pending_packet_revision IS NOT NULL AND pending_packet_revision>wait_packet_revision AND pending_context_fingerprint IS NOT NULL AND pending_context_fingerprint ~ '^[0-9a-f]{64}$' AND refresh_count BETWEEN 1 AND 3)
  OR (state<>'REFRESH_PENDING' AND pending_resume_request_id IS NULL AND pending_candidate_digest IS NULL AND pending_packet_revision IS NULL AND pending_context_fingerprint IS NULL));

ALTER TABLE agent_memory_thread_resume
 ADD COLUMN record_kind text,
 ADD COLUMN candidate_id text,
 ADD COLUMN wait_event_id text,
 ADD COLUMN operation_id text,
 ADD COLUMN attempt integer,
 ADD COLUMN canonical_request_hmac text,
 ADD COLUMN wait_phase text,
 ADD COLUMN old_packet_revision bigint,
 ADD COLUMN packet_revision bigint,
 ADD COLUMN execution_revision bigint,
 ADD COLUMN expected_current_context_fingerprint text,
 ADD COLUMN target_context_fingerprint text,
 ADD COLUMN candidate_digest text,
 ADD COLUMN issued_at bigint,
 ADD COLUMN expires_at bigint,
 ADD COLUMN candidate_phase text,
 ADD COLUMN current_packet_revision bigint,
 ADD COLUMN current_context_fingerprint text,
 ADD COLUMN refresh_count integer,
 ADD COLUMN receipt_state text,
 ADD COLUMN next_wait_event_id text,
 ADD COLUMN dispatch_allowed boolean,
 ADD COLUMN authorization_binding text,
 ADD CONSTRAINT ck_memory_thread_resume_shape CHECK(
  (record_kind IS NULL AND candidate_id IS NULL AND wait_event_id IS NULL AND operation_id IS NULL AND attempt IS NULL AND canonical_request_hmac IS NULL AND wait_phase IS NULL AND old_packet_revision IS NULL AND packet_revision IS NULL AND execution_revision IS NULL AND expected_current_context_fingerprint IS NULL AND target_context_fingerprint IS NULL AND candidate_digest IS NULL AND issued_at IS NULL AND expires_at IS NULL AND candidate_phase IS NULL AND current_packet_revision IS NULL AND current_context_fingerprint IS NULL AND refresh_count IS NULL AND receipt_state IS NULL AND next_wait_event_id IS NULL AND dispatch_allowed IS NULL AND authorization_binding IS NULL)
  OR (record_kind IS NOT NULL AND record_kind='RESUME' AND candidate_id IS NOT NULL AND length(candidate_id)>0 AND wait_event_id IS NOT NULL AND operation_id IS NOT NULL AND attempt IS NOT NULL AND attempt BETWEEN 1 AND 3 AND wait_phase IS NOT NULL AND wait_phase IN ('BEFORE_PREPARE','PREPARED','RESERVED') AND ((wait_phase='BEFORE_PREPARE' AND canonical_request_hmac IS NULL) OR (wait_phase IN ('PREPARED','RESERVED') AND canonical_request_hmac IS NOT NULL AND canonical_request_hmac ~ '^[0-9a-f]{64}$')) AND old_packet_revision IS NOT NULL AND old_packet_revision>0 AND packet_revision IS NOT NULL AND packet_revision>old_packet_revision AND execution_revision IS NOT NULL AND execution_revision>0 AND expected_current_context_fingerprint IS NOT NULL AND expected_current_context_fingerprint ~ '^[0-9a-f]{64}$' AND target_context_fingerprint IS NOT NULL AND target_context_fingerprint ~ '^[0-9a-f]{64}$' AND candidate_digest IS NOT NULL AND candidate_digest ~ '^[0-9a-f]{64}$' AND issued_at IS NOT NULL AND expires_at IS NOT NULL AND issued_at<expires_at AND candidate_phase IS NOT NULL AND candidate_phase IN ('PENDING','ACKED','EXPIRED_UNAPPLIED','APPLIED_EXPIRED','ABORTED') AND current_packet_revision IS NOT NULL AND current_packet_revision>0 AND current_context_fingerprint IS NOT NULL AND current_context_fingerprint ~ '^[0-9a-f]{64}$' AND refresh_count IS NOT NULL AND refresh_count BETWEEN 1 AND 3 AND receipt_state IS NOT NULL AND receipt_state IN ('ACTIVE','WAITING_CONTEXT','REFRESH_PENDING','BLOCKED','EXPIRED','REVOKED','SCRUBBED','DELETED') AND dispatch_allowed IS NOT NULL)),
 ADD CONSTRAINT ck_memory_thread_resume_code CHECK(record_kind IS NULL OR result_code IN ('CONTEXT_REFRESHED','CPU_CONFIRMED','MEMORY_REFRESH_PENDING','MEMORY_RESUME_CONFLICT','MEMORY_WAIT_CONSUMED','MEMORY_REVISION_CONFLICT','MEMORY_REFRESH_PACKET_EXPIRED','CONTEXT_REFRESH_LIMIT','EXECUTION_EXPIRED','SOURCE_CHANGED','SOURCE_REVOKED','ACCESS_REVOKED','CONTINUATION_AUTH_UNSUPPORTED','MEMORY_REFRESH_CAPABILITY_UNSUPPORTED','MEMORY_REFRESH_SCHEMA_REQUIRED','MEMORY_AUTHORITY_UNAVAILABLE','CONTEXT_INTERNAL_AUTH_REQUIRED','CONTEXT_SCOPE_MISMATCH','MEMORY_RESULT_UNAVAILABLE')),
 ADD CONSTRAINT ck_memory_thread_resume_legacy_code CHECK(record_kind IS NOT NULL OR result_code NOT IN ('CONTEXT_REFRESHED','MEMORY_REFRESH_PENDING','MEMORY_REFRESH_PACKET_EXPIRED')),
 ADD CONSTRAINT ck_memory_thread_resume_key CHECK(CASE WHEN record_kind='RESUME' THEN resume_request_id::jsonb=jsonb_build_array('memory-thread-receipt/2','RESUME',candidate_id) ELSE TRUE END),
 ADD CONSTRAINT ck_memory_thread_resume_phase CHECK(record_kind IS NULL
  OR (candidate_phase='PENDING' AND result_code='MEMORY_REFRESH_PENDING' AND receipt_state='REFRESH_PENDING' AND dispatch_allowed=FALSE AND authorization_binding IS NULL AND next_wait_event_id IS NULL AND current_packet_revision=old_packet_revision AND current_context_fingerprint=expected_current_context_fingerprint)
  OR (candidate_phase='ACKED' AND result_code='CONTEXT_REFRESHED' AND receipt_state='ACTIVE' AND current_packet_revision=packet_revision AND current_context_fingerprint=target_context_fingerprint AND authorization_binding IS NOT NULL AND authorization_binding='ACKED' AND next_wait_event_id IS NULL)
  OR (candidate_phase='EXPIRED_UNAPPLIED' AND result_code='MEMORY_REFRESH_PACKET_EXPIRED' AND current_packet_revision=old_packet_revision AND current_context_fingerprint=expected_current_context_fingerprint AND dispatch_allowed=FALSE AND authorization_binding IS NULL AND next_wait_event_id IS NULL AND ((refresh_count<3 AND receipt_state='WAITING_CONTEXT') OR (refresh_count=3 AND receipt_state='BLOCKED')))
  OR (candidate_phase='APPLIED_EXPIRED' AND result_code='MEMORY_REFRESH_PACKET_EXPIRED' AND current_packet_revision=packet_revision AND current_context_fingerprint=target_context_fingerprint AND dispatch_allowed=FALSE AND authorization_binding IS NOT NULL AND authorization_binding='ALIGN_ONLY' AND ((refresh_count<3 AND receipt_state='WAITING_CONTEXT' AND next_wait_event_id IS NOT NULL AND next_wait_event_id<>wait_event_id) OR (receipt_state='BLOCKED' AND next_wait_event_id IS NULL)))
  OR (candidate_phase='ABORTED' AND result_code NOT IN ('CPU_CONFIRMED','CONTINUATION_AUTH_UNSUPPORTED','CONTEXT_REFRESHED','MEMORY_REFRESH_PENDING','MEMORY_REFRESH_PACKET_EXPIRED') AND receipt_state IN ('BLOCKED','EXPIRED','REVOKED','SCRUBBED','DELETED') AND dispatch_allowed=FALSE AND authorization_binding IS NULL AND next_wait_event_id IS NULL));
CREATE UNIQUE INDEX uk_memory_thread_refresh_candidate ON agent_memory_thread_resume(tenant_id,execution_id,candidate_id) WHERE record_kind='RESUME';
CREATE UNIQUE INDEX uk_memory_thread_refresh_pending ON agent_memory_thread_resume(tenant_id,execution_id) WHERE record_kind='RESUME' AND candidate_phase='PENDING';

CREATE FUNCTION memory_thread_refresh_receipt_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE e agent_memory_thread_execution%ROWTYPE;
 legacy_key jsonb;
 legacy_erasure boolean := FALSE;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'MEMORY_REFRESH_DELETE_FORBIDDEN'; END IF;
 IF TG_OP='UPDATE' THEN
  IF OLD.record_kind IS NULL THEN
   -- 旧 ERASURE 只允许其原 DELETE_PENDING→DELETED 收口；旧 RESUME 成功/拒绝回执不可改写。
   IF (to_jsonb(NEW)-'result_code') IS DISTINCT FROM (to_jsonb(OLD)-'result_code') THEN RAISE EXCEPTION 'MEMORY_REFRESH_LEGACY_RECEIPT_IMMUTABLE'; END IF;
   IF NEW.result_code IS DISTINCT FROM OLD.result_code THEN
    IF OLD.result_code='DELETE_PENDING' AND NEW.result_code='DELETED' AND pg_input_is_valid(OLD.resume_request_id,'jsonb') THEN
     legacy_key := OLD.resume_request_id::jsonb;
     IF jsonb_typeof(legacy_key)='array' THEN
      legacy_erasure := (jsonb_array_length(legacy_key)=3 AND jsonb_typeof(legacy_key->0)='string' AND legacy_key->>0='memory-thread-receipt/2' AND jsonb_typeof(legacy_key->1)='string' AND legacy_key->>1='ERASURE' AND jsonb_typeof(legacy_key->2)='string' AND length(legacy_key->>2)>0 AND legacy_key->>2 !~ '^[[:space:]]*$') IS TRUE;
     END IF;
    END IF;
    IF legacy_erasure IS NOT TRUE THEN RAISE EXCEPTION 'MEMORY_REFRESH_LEGACY_RECEIPT_IMMUTABLE'; END IF;
   END IF;
   RETURN NEW;
  END IF;
  IF OLD.candidate_phase<>'PENDING' AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN RAISE EXCEPTION 'MEMORY_REFRESH_TERMINAL_IMMUTABLE'; END IF;
  IF (NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR NEW.execution_id IS DISTINCT FROM OLD.execution_id OR NEW.resume_request_id IS DISTINCT FROM OLD.resume_request_id OR NEW.request_hash IS DISTINCT FROM OLD.request_hash OR NEW.receipt_ref IS DISTINCT FROM OLD.receipt_ref OR NEW.record_kind IS DISTINCT FROM OLD.record_kind OR NEW.candidate_id IS DISTINCT FROM OLD.candidate_id OR NEW.wait_event_id IS DISTINCT FROM OLD.wait_event_id OR NEW.operation_id IS DISTINCT FROM OLD.operation_id OR NEW.attempt IS DISTINCT FROM OLD.attempt OR NEW.canonical_request_hmac IS DISTINCT FROM OLD.canonical_request_hmac OR NEW.wait_phase IS DISTINCT FROM OLD.wait_phase OR NEW.old_packet_revision IS DISTINCT FROM OLD.old_packet_revision OR NEW.packet_revision IS DISTINCT FROM OLD.packet_revision OR NEW.execution_revision IS DISTINCT FROM OLD.execution_revision OR NEW.expected_current_context_fingerprint IS DISTINCT FROM OLD.expected_current_context_fingerprint OR NEW.target_context_fingerprint IS DISTINCT FROM OLD.target_context_fingerprint OR NEW.candidate_digest IS DISTINCT FROM OLD.candidate_digest OR NEW.issued_at IS DISTINCT FROM OLD.issued_at OR NEW.expires_at IS DISTINCT FROM OLD.expires_at OR NEW.refresh_count IS DISTINCT FROM OLD.refresh_count) THEN RAISE EXCEPTION 'MEMORY_REFRESH_ANCHOR_IMMUTABLE'; END IF;
  IF NEW.candidate_phase IS DISTINCT FROM OLD.candidate_phase AND NEW.candidate_phase NOT IN ('ACKED','EXPIRED_UNAPPLIED','APPLIED_EXPIRED','ABORTED') THEN RAISE EXCEPTION 'MEMORY_REFRESH_PHASE_REGRESSION'; END IF;
 END IF;
 IF NEW.record_kind='RESUME' THEN
  SELECT * INTO STRICT e FROM agent_memory_thread_execution WHERE tenant_id=NEW.tenant_id AND execution_id=NEW.execution_id FOR UPDATE;
  IF TG_OP='INSERT' AND (NEW.candidate_phase<>'PENDING' OR e.state<>'WAITING_CONTEXT' OR e.wait_status<>'READY' OR NEW.wait_event_id IS DISTINCT FROM e.wait_event_id OR NEW.old_packet_revision IS DISTINCT FROM e.packet_revision OR NEW.expected_current_context_fingerprint IS DISTINCT FROM e.current_context_fingerprint OR NEW.expected_current_context_fingerprint IS DISTINCT FROM e.wait_context_fingerprint OR NEW.execution_revision<>e.execution_revision OR NEW.refresh_count<>e.refresh_count+1 OR NEW.refresh_count>3 OR NEW.wait_phase<>e.wait_phase OR NEW.expires_at>e.original_deadline) THEN RAISE EXCEPTION 'MEMORY_REFRESH_CANDIDATE_BINDING_REQUIRED'; END IF;
  IF TG_OP='UPDATE' AND OLD.candidate_phase='PENDING' AND NEW.candidate_phase<>'PENDING' AND (e.state<>'REFRESH_PENDING' OR e.pending_resume_request_id IS DISTINCT FROM NEW.candidate_id OR e.refresh_count<>NEW.refresh_count) THEN RAISE EXCEPTION 'MEMORY_REFRESH_PENDING_REQUIRED'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_memory_thread_refresh_receipt BEFORE INSERT OR UPDATE OR DELETE ON agent_memory_thread_resume FOR EACH ROW EXECUTE FUNCTION memory_thread_refresh_receipt_guard();

CREATE FUNCTION memory_thread_refresh_execution_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r agent_memory_thread_resume%ROWTYPE;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'MEMORY_REFRESH_DELETE_FORBIDDEN'; END IF;
 IF (NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR NEW.execution_id IS DISTINCT FROM OLD.execution_id OR NEW.runtime_id IS DISTINCT FROM OLD.runtime_id OR NEW.root_thread_id IS DISTINCT FROM OLD.root_thread_id OR NEW.scope IS DISTINCT FROM OLD.scope OR NEW.operation_hash IS DISTINCT FROM OLD.operation_hash OR NEW.execution_revision IS DISTINCT FROM OLD.execution_revision OR NEW.dependencies IS DISTINCT FROM OLD.dependencies OR NEW.backend_ids IS DISTINCT FROM OLD.backend_ids OR NEW.original_deadline IS DISTINCT FROM OLD.original_deadline OR NEW.semantic_digest IS DISTINCT FROM OLD.semantic_digest OR NEW.checkpoint_mode IS DISTINCT FROM OLD.checkpoint_mode) THEN RAISE EXCEPTION 'MEMORY_REFRESH_ANCHOR_IMMUTABLE'; END IF;
 IF NEW.refresh_count<OLD.refresh_count OR NEW.refresh_count>3 OR NEW.refresh_count>OLD.refresh_count+1 OR NEW.fence_revision<OLD.fence_revision THEN RAISE EXCEPTION 'MEMORY_REFRESH_COUNTER_REGRESSION'; END IF;
 IF OLD.state IN ('BLOCKED','REVOKED','SCRUBBED','DELETED','EXPIRED') AND NEW.state IN ('ACTIVE','WAITING_CONTEXT','REFRESH_PENDING') THEN RAISE EXCEPTION 'MEMORY_REFRESH_TERMINAL_RESURRECTION'; END IF;
 IF OLD.state='DELETED' AND NEW.state<>'DELETED' OR OLD.state='SCRUBBED' AND NEW.state NOT IN ('SCRUBBED','DELETED') OR OLD.state='REVOKED' AND NEW.state NOT IN ('REVOKED','SCRUBBED','DELETED') THEN RAISE EXCEPTION 'MEMORY_REFRESH_TERMINAL_RESURRECTION'; END IF;
 IF OLD.state='ACTIVE' AND NEW.state='WAITING_CONTEXT' THEN
  IF NEW.wait_status<>'BUILDING' OR NEW.wait_event_id IS NULL OR NEW.current_context_fingerprint IS NULL OR NEW.wait_packet_revision<>OLD.packet_revision OR NEW.wait_context_fingerprint IS DISTINCT FROM NEW.current_context_fingerprint OR NEW.fence_revision<>OLD.fence_revision+1 OR NEW.refresh_count<>OLD.refresh_count THEN RAISE EXCEPTION 'MEMORY_REFRESH_WAIT_BINDING_REQUIRED'; END IF;
 END IF;
 IF NEW.state='REFRESH_PENDING' AND OLD.state<>'REFRESH_PENDING' THEN
  IF NEW.wait_event_id IS DISTINCT FROM OLD.wait_event_id OR NEW.wait_status IS DISTINCT FROM OLD.wait_status OR NEW.wait_context_fingerprint IS DISTINCT FROM OLD.wait_context_fingerprint OR NEW.wait_packet_revision IS DISTINCT FROM OLD.wait_packet_revision OR NEW.wait_phase IS DISTINCT FROM OLD.wait_phase OR NEW.wait_checkpoint_ns IS DISTINCT FROM OLD.wait_checkpoint_ns OR NEW.wait_checkpoint_id IS DISTINCT FROM OLD.wait_checkpoint_id THEN RAISE EXCEPTION 'MEMORY_REFRESH_WAIT_IMMUTABLE'; END IF;
  SELECT * INTO STRICT r FROM agent_memory_thread_resume WHERE tenant_id=NEW.tenant_id AND execution_id=NEW.execution_id AND record_kind='RESUME' AND candidate_id=NEW.pending_resume_request_id;
  IF OLD.state<>'WAITING_CONTEXT' OR OLD.wait_status<>'READY' OR r.candidate_phase<>'PENDING' OR r.wait_event_id IS DISTINCT FROM OLD.wait_event_id OR r.candidate_digest IS DISTINCT FROM NEW.pending_candidate_digest OR r.packet_revision IS DISTINCT FROM NEW.pending_packet_revision OR r.target_context_fingerprint IS DISTINCT FROM NEW.pending_context_fingerprint OR r.refresh_count<>NEW.refresh_count OR NEW.refresh_count<>OLD.refresh_count+1 OR NEW.fence_revision<>OLD.fence_revision+1 THEN RAISE EXCEPTION 'MEMORY_REFRESH_PENDING_BINDING_REQUIRED'; END IF;
 END IF;
 IF OLD.state='REFRESH_PENDING' AND NEW.state IN ('ACTIVE','WAITING_CONTEXT','BLOCKED') THEN
  SELECT * INTO STRICT r FROM agent_memory_thread_resume WHERE tenant_id=OLD.tenant_id AND execution_id=OLD.execution_id AND record_kind='RESUME' AND candidate_id=OLD.pending_resume_request_id;
  IF r.candidate_phase='PENDING' OR r.receipt_state<>NEW.state OR r.current_packet_revision<>NEW.packet_revision OR r.current_context_fingerprint IS DISTINCT FROM NEW.current_context_fingerprint OR r.refresh_count<>NEW.refresh_count THEN RAISE EXCEPTION 'MEMORY_REFRESH_FINAL_RECEIPT_REQUIRED'; END IF;
  IF NEW.state='ACTIVE' AND r.candidate_phase<>'ACKED' THEN RAISE EXCEPTION 'MEMORY_REFRESH_NO_ACTIVE_ALIGNMENT'; END IF;
  IF NEW.state='WAITING_CONTEXT' AND (NEW.wait_phase IS DISTINCT FROM OLD.wait_phase OR NEW.wait_phase IS DISTINCT FROM r.wait_phase) THEN RAISE EXCEPTION 'MEMORY_REFRESH_WAIT_IMMUTABLE'; END IF;
  IF NEW.state='WAITING_CONTEXT' AND ((r.candidate_phase='EXPIRED_UNAPPLIED' AND (NEW.wait_status<>'READY' OR NEW.wait_event_id IS DISTINCT FROM OLD.wait_event_id)) OR (r.candidate_phase='APPLIED_EXPIRED' AND (NEW.wait_event_id IS DISTINCT FROM r.next_wait_event_id OR NEW.wait_context_fingerprint IS DISTINCT FROM r.current_context_fingerprint OR NEW.wait_packet_revision<>r.current_packet_revision OR NEW.wait_status<>'READY'))) THEN RAISE EXCEPTION 'MEMORY_REFRESH_NEXT_WAIT_REQUIRED'; END IF;
  IF NEW.refresh_count=3 AND r.candidate_phase IN ('EXPIRED_UNAPPLIED','APPLIED_EXPIRED') AND (NEW.state<>'BLOCKED' OR NEW.terminal_reason IS DISTINCT FROM 'CONTEXT_REFRESH_LIMIT') THEN RAISE EXCEPTION 'MEMORY_REFRESH_LIMIT_REQUIRED'; END IF;
 END IF;
 IF NEW.state='ACTIVE' AND OLD.state NOT IN ('ACTIVE','REFRESH_PENDING') THEN RAISE EXCEPTION 'MEMORY_REFRESH_PENDING_REQUIRED'; END IF;
 IF NEW.packet_revision IS DISTINCT FROM OLD.packet_revision OR NEW.packet_expires_at IS DISTINCT FROM OLD.packet_expires_at OR (OLD.current_context_fingerprint IS NOT NULL AND NEW.current_context_fingerprint IS DISTINCT FROM OLD.current_context_fingerprint) THEN
  IF OLD.state<>'REFRESH_PENDING' OR NEW.state NOT IN ('ACTIVE','WAITING_CONTEXT','BLOCKED') THEN RAISE EXCEPTION 'MEMORY_REFRESH_ALIGNMENT_REQUIRED'; END IF;
  IF NEW.packet_revision<>OLD.pending_packet_revision OR NEW.current_context_fingerprint IS DISTINCT FROM OLD.pending_context_fingerprint OR NEW.packet_expires_at IS DISTINCT FROM r.expires_at THEN RAISE EXCEPTION 'MEMORY_REFRESH_ALIGNMENT_REQUIRED'; END IF;
 END IF;
 IF NEW.refresh_count>OLD.refresh_count AND NEW.state<>'REFRESH_PENDING' AND NOT(OLD.state='ACTIVE' AND NEW.state='ACTIVE' AND OLD.wait_status IS NULL AND NEW.wait_status IS NULL) THEN RAISE EXCEPTION 'MEMORY_REFRESH_PENDING_REQUIRED'; END IF;
 IF OLD.state='REFRESH_PENDING' AND NEW.state='REFRESH_PENDING' AND (NEW.pending_resume_request_id IS DISTINCT FROM OLD.pending_resume_request_id OR NEW.pending_candidate_digest IS DISTINCT FROM OLD.pending_candidate_digest OR NEW.pending_packet_revision IS DISTINCT FROM OLD.pending_packet_revision OR NEW.pending_context_fingerprint IS DISTINCT FROM OLD.pending_context_fingerprint OR NEW.refresh_count<>OLD.refresh_count) THEN RAISE EXCEPTION 'MEMORY_REFRESH_PENDING_IMMUTABLE'; END IF;
 IF NEW.wait_event_id IS NOT DISTINCT FROM OLD.wait_event_id AND OLD.wait_status IS NOT NULL AND (NEW.wait_context_fingerprint IS DISTINCT FROM OLD.wait_context_fingerprint OR NEW.wait_packet_revision IS DISTINCT FROM OLD.wait_packet_revision OR NEW.wait_phase IS DISTINCT FROM OLD.wait_phase) THEN RAISE EXCEPTION 'MEMORY_REFRESH_WAIT_IMMUTABLE'; END IF;
 IF OLD.wait_status='READY' AND NEW.wait_event_id IS NOT DISTINCT FROM OLD.wait_event_id AND (NEW.wait_checkpoint_ns IS DISTINCT FROM OLD.wait_checkpoint_ns OR NEW.wait_checkpoint_id IS DISTINCT FROM OLD.wait_checkpoint_id) AND NEW.state<>'ACTIVE' THEN RAISE EXCEPTION 'MEMORY_REFRESH_CHECKPOINT_IMMUTABLE'; END IF;
 IF OLD.state='REFRESH_PENDING' AND NEW.state='REFRESH_PENDING' AND NEW.wait_event_id IS DISTINCT FROM OLD.wait_event_id THEN RAISE EXCEPTION 'MEMORY_REFRESH_WAIT_IMMUTABLE'; END IF;
 IF OLD.state='WAITING_CONTEXT' AND NEW.state='WAITING_CONTEXT' AND (NEW.wait_event_id IS DISTINCT FROM OLD.wait_event_id OR (OLD.wait_status='READY' AND NEW.wait_status<>'READY')) THEN RAISE EXCEPTION 'MEMORY_REFRESH_WAIT_IMMUTABLE'; END IF;
 IF OLD.current_context_fingerprint IS NULL AND NEW.current_context_fingerprint IS NOT NULL AND NOT(OLD.state='ACTIVE' AND NEW.state='WAITING_CONTEXT') THEN RAISE EXCEPTION 'MEMORY_REFRESH_WAIT_BINDING_REQUIRED'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_memory_thread_refresh_execution BEFORE UPDATE OR DELETE ON agent_memory_thread_execution FOR EACH ROW EXECUTE FUNCTION memory_thread_refresh_execution_guard();
COMMIT;
