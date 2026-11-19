-- M2 P1/P4；新增本模块四表；默认不开摘要，不改既有迁移或业务表。
-- 执行前独立审阅precheck/up/verify/rollback；只root任务自有loopback随机schema演练。
-- DDL隐式提交，持锁受5秒限制；已有使用数据拒绝回滚。无共享库执行授权。
SET SESSION lock_wait_timeout=5;
SET SESSION innodb_lock_wait_timeout=5;
CREATE TABLE ai_memory_summary_watermark (
 tenant_id VARBINARY(512) NOT NULL, scope_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 user_id VARBINARY(512) NOT NULL, domain VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 top_level_agent_id VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,session_id VARBINARY(512) NOT NULL,
 revision BIGINT UNSIGNED NOT NULL DEFAULT 0,source_revision BIGINT UNSIGNED NOT NULL DEFAULT 0,
 next_sequence BIGINT UNSIGNED NOT NULL DEFAULT 1,commit_revision BIGINT UNSIGNED NOT NULL DEFAULT 0,
 covered_through BIGINT UNSIGNED NOT NULL DEFAULT 0,deletion_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0,
 PRIMARY KEY(tenant_id,scope_key),UNIQUE KEY uk_summary_scope(tenant_id,user_id,domain,session_id),
 CONSTRAINT ck_summary_scope CHECK(domain IN ('operations','customer-service') AND top_level_agent_id=domain AND OCTET_LENGTH(user_id)>0 AND OCTET_LENGTH(session_id)>0 AND REGEXP_LIKE(scope_key,'^[0-9a-f]{64}$','c')),
 CONSTRAINT ck_summary_watermark CHECK(next_sequence>0 AND covered_through<next_sequence)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
CREATE TABLE ai_memory_summary_source (
 tenant_id VARBINARY(512) NOT NULL,scope_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 message_id VARBINARY(512) NOT NULL,content_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 sequence_no BIGINT UNSIGNED NOT NULL,group_id VARBINARY(512) NOT NULL,group_members_json JSON NOT NULL,
 dependencies_json JSON NOT NULL,policy_id VARBINARY(512) NOT NULL,policy_version_id VARBINARY(512) NOT NULL,expires_at DATETIME(6) NOT NULL,
 PRIMARY KEY(tenant_id,scope_key,message_id),UNIQUE KEY uk_summary_sequence(tenant_id,scope_key,sequence_no),
 UNIQUE KEY uk_summary_message(tenant_id,message_id),
 CONSTRAINT fk_summary_source_scope FOREIGN KEY(tenant_id,scope_key) REFERENCES ai_memory_summary_watermark(tenant_id,scope_key),
 CONSTRAINT fk_summary_message_source FOREIGN KEY(tenant_id,message_id) REFERENCES ai_memory_source(tenant_id,id),
 CONSTRAINT ck_summary_source CHECK(sequence_no>0 AND OCTET_LENGTH(message_id)>0 AND OCTET_LENGTH(group_id)>0 AND REGEXP_LIKE(content_hash,'^[0-9a-f]{64}$','c') AND JSON_TYPE(group_members_json)='ARRAY' AND JSON_LENGTH(group_members_json)>0 AND JSON_TYPE(dependencies_json)='ARRAY' AND JSON_LENGTH(dependencies_json)>0)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
CREATE TABLE ai_memory_summary_plan (
 tenant_id VARBINARY(512) NOT NULL,scope_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,id VARBINARY(512) NOT NULL,
 execution_id VARBINARY(512) NOT NULL,task_id VARBINARY(512) NOT NULL,original_session_ref VARBINARY(512) NOT NULL,
 policy_id VARBINARY(512) NOT NULL,policy_version_id VARBINARY(512) NOT NULL,
 session_revision BIGINT UNSIGNED NOT NULL,source_revision BIGINT UNSIGNED NOT NULL,commit_revision BIGINT UNSIGNED NOT NULL,
 original_deadline BIGINT UNSIGNED NOT NULL,expires_at BIGINT UNSIGNED NOT NULL,
 fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,transport_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,key_version VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 encrypted_payload LONGBLOB NULL,nonce BINARY(12) NULL,auth_tag BINARY(16) NULL,content_hmac BINARY(32) NULL,
 state VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 PRIMARY KEY(tenant_id,id),UNIQUE KEY uk_summary_plan_task(tenant_id,task_id),UNIQUE KEY uk_summary_plan_scope(tenant_id,scope_key,id),
 CONSTRAINT fk_summary_plan_scope FOREIGN KEY(tenant_id,scope_key) REFERENCES ai_memory_summary_watermark(tenant_id,scope_key),
 CONSTRAINT fk_summary_plan_execution FOREIGN KEY(tenant_id,execution_id) REFERENCES ai_memory_packet(tenant_id,execution_id),
 CONSTRAINT ck_summary_plan CHECK(OCTET_LENGTH(id)>0 AND OCTET_LENGTH(original_session_ref)>0 AND original_deadline>0 AND expires_at>0 AND REGEXP_LIKE(fingerprint,'^[0-9a-f]{64}$','c') AND state IN ('FROZEN','COMMITTED','STALE','SCRUBBED')),
 CONSTRAINT ck_summary_transport_fp CHECK(transport_fingerprint IS NULL OR REGEXP_LIKE(transport_fingerprint,'^[0-9a-f]{64}$','c')),
 CONSTRAINT ck_summary_plan_body CHECK((state='SCRUBBED' AND encrypted_payload IS NULL AND nonce IS NULL AND auth_tag IS NULL AND content_hmac IS NULL) OR (state<>'SCRUBBED' AND encrypted_payload IS NOT NULL AND nonce IS NOT NULL AND auth_tag IS NOT NULL AND content_hmac IS NOT NULL))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
CREATE TABLE ai_memory_summary_segment (
 tenant_id VARBINARY(512) NOT NULL,scope_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,id VARBINARY(512) NOT NULL,plan_id VARBINARY(512) NOT NULL,
 first_sequence BIGINT UNSIGNED NOT NULL,last_sequence BIGINT UNSIGNED NOT NULL,commit_revision BIGINT UNSIGNED NOT NULL,expires_at BIGINT UNSIGNED NOT NULL,
 payload_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,key_version VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 encrypted_payload LONGBLOB NULL,nonce BINARY(12) NULL,auth_tag BINARY(16) NULL,content_hmac BINARY(32) NULL,
 state VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 PRIMARY KEY(tenant_id,id),UNIQUE KEY uk_summary_segment_plan(tenant_id,scope_key,plan_id),
 UNIQUE KEY uk_summary_segment_commit(tenant_id,scope_key,commit_revision),
 CONSTRAINT fk_summary_segment_plan FOREIGN KEY(tenant_id,scope_key,plan_id) REFERENCES ai_memory_summary_plan(tenant_id,scope_key,id),
 CONSTRAINT ck_summary_segment CHECK(first_sequence>0 AND last_sequence>=first_sequence AND commit_revision>0 AND expires_at>0 AND REGEXP_LIKE(payload_digest,'^[0-9a-f]{64}$','c') AND state IN ('COMMITTED','SCRUBBED')),
 CONSTRAINT ck_summary_segment_body CHECK((state='SCRUBBED' AND encrypted_payload IS NULL AND nonce IS NULL AND auth_tag IS NULL AND content_hmac IS NULL) OR (state='COMMITTED' AND encrypted_payload IS NOT NULL AND nonce IS NOT NULL AND auth_tag IS NOT NULL AND content_hmac IS NOT NULL))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
DELIMITER $$
CREATE TRIGGER trg_summary_watermark_update BEFORE UPDATE ON ai_memory_summary_watermark FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.scope_key<=>OLD.scope_key) OR NOT(NEW.user_id<=>OLD.user_id) OR NOT(NEW.domain<=>OLD.domain) OR NOT(NEW.top_level_agent_id<=>OLD.top_level_agent_id) OR NOT(NEW.session_id<=>OLD.session_id) OR NEW.revision<OLD.revision OR NEW.source_revision<OLD.source_revision OR NEW.next_sequence<OLD.next_sequence OR NEW.commit_revision<OLD.commit_revision OR NEW.covered_through<OLD.covered_through OR NEW.deletion_epoch<OLD.deletion_epoch THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SUMMARY_WATERMARK_REGRESSION'; END IF;
END$$
CREATE TRIGGER trg_summary_source_update BEFORE UPDATE ON ai_memory_summary_source FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SUMMARY_SOURCE_IMMUTABLE'; END$$
CREATE TRIGGER trg_summary_plan_update BEFORE UPDATE ON ai_memory_summary_plan FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.scope_key<=>OLD.scope_key) OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.execution_id<=>OLD.execution_id) OR NOT(NEW.task_id<=>OLD.task_id) OR NOT(NEW.original_session_ref<=>OLD.original_session_ref) OR NOT(NEW.policy_id<=>OLD.policy_id) OR NOT(NEW.policy_version_id<=>OLD.policy_version_id) OR NOT(NEW.session_revision<=>OLD.session_revision) OR NOT(NEW.source_revision<=>OLD.source_revision) OR NOT(NEW.commit_revision<=>OLD.commit_revision) OR NOT(NEW.original_deadline<=>OLD.original_deadline) OR NOT(NEW.expires_at<=>OLD.expires_at) OR NOT(NEW.fingerprint<=>OLD.fingerprint) OR NOT(NEW.key_version<=>OLD.key_version) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SUMMARY_PLAN_IMMUTABLE'; END IF;
 IF OLD.transport_fingerprint IS NULL AND NEW.transport_fingerprint IS NOT NULL AND OLD.state<>'FROZEN' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='DERIVE_BINDING_CONFLICT'; END IF;
 IF OLD.transport_fingerprint IS NOT NULL AND NOT(NEW.transport_fingerprint<=>OLD.transport_fingerprint) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='DERIVE_BINDING_CONFLICT'; END IF;
 IF NOT((OLD.state='FROZEN' AND NEW.state IN ('COMMITTED','STALE','SCRUBBED')) OR (OLD.state IN ('COMMITTED','STALE') AND NEW.state='SCRUBBED') OR (OLD.state='FROZEN' AND NEW.state='FROZEN' AND NEW.transport_fingerprint IS NOT NULL)) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SUMMARY_TERMINAL_IMMUTABLE'; END IF;
 IF NEW.state<>'SCRUBBED' AND (NOT(NEW.encrypted_payload<=>OLD.encrypted_payload) OR NOT(NEW.nonce<=>OLD.nonce) OR NOT(NEW.auth_tag<=>OLD.auth_tag) OR NOT(NEW.content_hmac<=>OLD.content_hmac)) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SUMMARY_BODY_IMMUTABLE'; END IF;
END$$
CREATE TRIGGER trg_summary_segment_update BEFORE UPDATE ON ai_memory_summary_segment FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.scope_key<=>OLD.scope_key) OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.plan_id<=>OLD.plan_id) OR NOT(NEW.first_sequence<=>OLD.first_sequence) OR NOT(NEW.last_sequence<=>OLD.last_sequence) OR NOT(NEW.commit_revision<=>OLD.commit_revision) OR NOT(NEW.expires_at<=>OLD.expires_at) OR NOT(NEW.payload_digest<=>OLD.payload_digest) OR NOT(NEW.key_version<=>OLD.key_version) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SUMMARY_SEGMENT_IMMUTABLE'; END IF;
 IF NOT(OLD.state='COMMITTED' AND NEW.state='SCRUBBED') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SUMMARY_TERMINAL_IMMUTABLE'; END IF;
 IF NEW.state<>'SCRUBBED' AND (NOT(NEW.encrypted_payload<=>OLD.encrypted_payload) OR NOT(NEW.nonce<=>OLD.nonce) OR NOT(NEW.auth_tag<=>OLD.auth_tag) OR NOT(NEW.content_hmac<=>OLD.content_hmac)) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SUMMARY_BODY_IMMUTABLE'; END IF;
END$$
CREATE TRIGGER trg_summary_watermark_delete BEFORE DELETE ON ai_memory_summary_watermark FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SUMMARY_DELETE_FORBIDDEN'; END$$
CREATE TRIGGER trg_summary_source_delete BEFORE DELETE ON ai_memory_summary_source FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SUMMARY_DELETE_FORBIDDEN'; END$$
CREATE TRIGGER trg_summary_plan_delete BEFORE DELETE ON ai_memory_summary_plan FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SUMMARY_DELETE_FORBIDDEN'; END$$
CREATE TRIGGER trg_summary_segment_delete BEFORE DELETE ON ai_memory_summary_segment FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SUMMARY_DELETE_FORBIDDEN'; END$$
CREATE TRIGGER trg_summary_source_invalidation AFTER UPDATE ON ai_memory_source FOR EACH ROW
BEGIN
 IF NEW.grant_epoch>OLD.grant_epoch OR NEW.source_epoch>OLD.source_epoch OR NEW.deletion_epoch>OLD.deletion_epoch
  OR (OLD.retention_deadline IS NOT NULL AND (NEW.retention_deadline IS NULL OR NEW.retention_deadline<OLD.retention_deadline)) THEN
  UPDATE ai_memory_summary_segment g SET state='SCRUBBED',encrypted_payload=NULL,nonce=NULL,auth_tag=NULL,content_hmac=NULL
   WHERE g.tenant_id=NEW.tenant_id AND g.state='COMMITTED' AND EXISTS(
    SELECT 1 FROM ai_memory_summary_source m WHERE m.tenant_id=g.tenant_id AND m.scope_key=g.scope_key
     AND JSON_CONTAINS(m.dependencies_json,JSON_OBJECT('source_id',CONVERT(NEW.id USING utf8mb4))));
  UPDATE ai_memory_summary_plan p SET state='SCRUBBED',encrypted_payload=NULL,nonce=NULL,auth_tag=NULL,content_hmac=NULL
   WHERE p.tenant_id=NEW.tenant_id AND p.state<>'SCRUBBED' AND EXISTS(
    SELECT 1 FROM ai_memory_summary_source m WHERE m.tenant_id=p.tenant_id AND m.scope_key=p.scope_key
     AND JSON_CONTAINS(m.dependencies_json,JSON_OBJECT('source_id',CONVERT(NEW.id USING utf8mb4))));
 END IF;
END$$
DELIMITER ;
