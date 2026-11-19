-- D29：有界案例/人工回归签认/现有资产晋升引用；默认关闭，不隐式生成/部署。
SET SESSION lock_wait_timeout=5;
SET SESSION innodb_lock_wait_timeout=5;
CREATE TABLE ai_memory_episode (
 tenant_id VARBINARY(512) NOT NULL,id VARBINARY(512) NOT NULL,owner_id VARBINARY(512) NOT NULL,
 domain VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,session_id VARBINARY(512) NULL,execution_id VARBINARY(512) NOT NULL,
 scope_json JSON NOT NULL,dependencies_json JSON NOT NULL,policy_id VARBINARY(512) NOT NULL,policy_version_id VARBINARY(512) NOT NULL,
 status VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,revision BIGINT UNSIGNED NOT NULL DEFAULT 0,expires_at DATETIME(6) NOT NULL,
 key_version VARBINARY(128) NOT NULL,encrypted_payload MEDIUMBLOB NULL,nonce BINARY(12) NULL,auth_tag BINARY(16) NULL,content_hmac BINARY(32) NULL,
 share_scope_id VARBINARY(512) NULL,share_owner_session_ref VARBINARY(512) NULL,shared_key_version VARBINARY(128) NULL,shared_payload MEDIUMBLOB NULL,shared_nonce BINARY(12) NULL,shared_tag BINARY(16) NULL,shared_hmac BINARY(32) NULL,
 share_approver_id VARBINARY(512) NULL,request_id VARBINARY(512) NOT NULL,fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 PRIMARY KEY(tenant_id,id),UNIQUE KEY uk_episode_request(tenant_id,request_id),KEY ix_episode_owner(tenant_id,owner_id,domain),
 CONSTRAINT fk_episode_execution FOREIGN KEY(tenant_id,execution_id) REFERENCES ai_memory_packet(tenant_id,execution_id),
 CONSTRAINT fk_episode_policy FOREIGN KEY(tenant_id,policy_id,policy_version_id) REFERENCES ai_memory_policy_version(tenant_id,policy_id,version_id),
 CONSTRAINT fk_episode_scope FOREIGN KEY(tenant_id,share_scope_id) REFERENCES ai_memory_sharing_scope(tenant_id,id),
 CONSTRAINT ck_episode_status CHECK(status IN ('CANDIDATE','CONFIRMED','REJECTED','SHARE_PENDING','SHARED','REVOKED')),
 CONSTRAINT ck_episode_source CHECK(domain IN ('operations','customer-service','hr') AND JSON_TYPE(scope_json)='OBJECT' AND JSON_TYPE(dependencies_json)='ARRAY' AND JSON_LENGTH(dependencies_json) BETWEEN 1 AND 512),
 CONSTRAINT ck_episode_body CHECK((status='REVOKED' AND encrypted_payload IS NULL AND nonce IS NULL AND auth_tag IS NULL AND content_hmac IS NULL AND shared_payload IS NULL AND shared_nonce IS NULL AND shared_tag IS NULL AND shared_hmac IS NULL) OR (status<>'REVOKED' AND encrypted_payload IS NOT NULL AND nonce IS NOT NULL AND auth_tag IS NOT NULL AND content_hmac IS NOT NULL)),
 CONSTRAINT ck_episode_shared CHECK(status NOT IN ('SHARE_PENDING','SHARED') OR (share_scope_id IS NOT NULL AND share_owner_session_ref IS NOT NULL AND shared_key_version IS NOT NULL AND shared_payload IS NOT NULL AND shared_nonce IS NOT NULL AND shared_tag IS NOT NULL AND shared_hmac IS NOT NULL)),
 CONSTRAINT ck_episode_approver CHECK(status<>'SHARED' OR (share_approver_id IS NOT NULL AND share_approver_id<>owner_id))
 ,CONSTRAINT ck_episode_bound CHECK((encrypted_payload IS NULL OR OCTET_LENGTH(encrypted_payload)<=524288) AND (shared_payload IS NULL OR OCTET_LENGTH(shared_payload)<=524288))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
CREATE TABLE ai_memory_episode_like (
 tenant_id VARBINARY(512) NOT NULL,episode_id VARBINARY(512) NOT NULL,user_id VARBINARY(512) NOT NULL,
 PRIMARY KEY(tenant_id,episode_id,user_id),CONSTRAINT fk_episode_like FOREIGN KEY(tenant_id,episode_id) REFERENCES ai_memory_episode(tenant_id,id)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
CREATE TABLE ai_memory_promotion (
 tenant_id VARBINARY(512) NOT NULL,id VARBINARY(512) NOT NULL,episode_id VARBINARY(512) NOT NULL,owner_id VARBINARY(512) NOT NULL,
 target_type VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,target_definition_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 target_version_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,candidate_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 status VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,revision BIGINT UNSIGNED NOT NULL DEFAULT 0,request_id VARBINARY(512) NOT NULL,
 fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,regression_suite_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,
 regression_suite_version VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,regression_report_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 total_cases INT UNSIGNED NOT NULL DEFAULT 0,passed_cases INT UNSIGNED NOT NULL DEFAULT 0,regression_reviewer_id VARBINARY(512) NULL,publisher_id VARBINARY(512) NULL,
 PRIMARY KEY(tenant_id,id),UNIQUE KEY uk_promotion_request(tenant_id,request_id),UNIQUE KEY uk_promotion_asset(target_type,target_version_id),
 CONSTRAINT fk_promotion_episode FOREIGN KEY(tenant_id,episode_id) REFERENCES ai_memory_episode(tenant_id,id),
 CONSTRAINT ck_promotion CHECK(target_type IN ('PROMPT','WORKFLOW','SKILL') AND status IN ('DRAFT','REGRESSION_PASSED','PUBLISHED','REVOKED') AND passed_cases<=total_cases),
 CONSTRAINT ck_promotion_regression CHECK(status NOT IN ('REGRESSION_PASSED','PUBLISHED') OR (regression_suite_id IS NOT NULL AND regression_suite_version IS NOT NULL AND regression_report_sha256 IS NOT NULL AND total_cases>0 AND total_cases=passed_cases AND regression_reviewer_id IS NOT NULL AND regression_reviewer_id<>owner_id)),
 CONSTRAINT ck_promotion_publisher CHECK(status<>'PUBLISHED' OR (publisher_id IS NOT NULL AND publisher_id<>owner_id AND publisher_id<>regression_reviewer_id))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
DELIMITER $$
CREATE TRIGGER trg_episode_update BEFORE UPDATE ON ai_memory_episode FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.owner_id<=>OLD.owner_id) OR NOT(NEW.domain<=>OLD.domain) OR NOT(NEW.session_id<=>OLD.session_id) OR NOT(NEW.execution_id<=>OLD.execution_id) OR NOT(NEW.scope_json<=>OLD.scope_json) OR NOT(NEW.dependencies_json<=>OLD.dependencies_json) OR NOT(NEW.policy_id<=>OLD.policy_id) OR NOT(NEW.policy_version_id<=>OLD.policy_version_id) OR NOT(NEW.expires_at<=>OLD.expires_at) OR NOT(NEW.key_version<=>OLD.key_version) OR NOT(NEW.request_id<=>OLD.request_id) OR NOT(NEW.fingerprint<=>OLD.fingerprint) OR NEW.revision<>OLD.revision+1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EPISODE_IMMUTABLE'; END IF;
 IF NOT((OLD.status='CANDIDATE' AND NEW.status IN ('CONFIRMED','REJECTED','REVOKED')) OR (OLD.status='CONFIRMED' AND NEW.status IN ('SHARE_PENDING','REVOKED')) OR (OLD.status='SHARE_PENDING' AND NEW.status IN ('SHARED','REVOKED')) OR (OLD.status IN ('SHARED','REJECTED') AND NEW.status='REVOKED')) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EPISODE_STATE_INVALID'; END IF;
 IF NEW.status<>'REVOKED' AND (NOT(NEW.encrypted_payload<=>OLD.encrypted_payload) OR NOT(NEW.nonce<=>OLD.nonce) OR NOT(NEW.auth_tag<=>OLD.auth_tag) OR NOT(NEW.content_hmac<=>OLD.content_hmac)) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EPISODE_BODY_IMMUTABLE'; END IF;
 IF OLD.shared_payload IS NOT NULL AND NEW.status<>'REVOKED' AND (NOT(NEW.shared_payload<=>OLD.shared_payload) OR NOT(NEW.shared_nonce<=>OLD.shared_nonce) OR NOT(NEW.shared_tag<=>OLD.shared_tag) OR NOT(NEW.shared_hmac<=>OLD.shared_hmac) OR NOT(NEW.share_scope_id<=>OLD.share_scope_id) OR NOT(NEW.share_owner_session_ref<=>OLD.share_owner_session_ref)) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EPISODE_SHARED_BODY_IMMUTABLE'; END IF;
END$$
CREATE TRIGGER trg_episode_delete BEFORE DELETE ON ai_memory_episode FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EPISODE_DELETE_FORBIDDEN'; END$$
CREATE TRIGGER trg_promotion_update BEFORE UPDATE ON ai_memory_promotion FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.episode_id<=>OLD.episode_id) OR NOT(NEW.owner_id<=>OLD.owner_id) OR NOT(NEW.target_type<=>OLD.target_type) OR NOT(NEW.target_definition_id<=>OLD.target_definition_id) OR NOT(NEW.target_version_id<=>OLD.target_version_id) OR NOT(NEW.candidate_digest<=>OLD.candidate_digest) OR NOT(NEW.request_id<=>OLD.request_id) OR NOT(NEW.fingerprint<=>OLD.fingerprint) OR NEW.revision<>OLD.revision+1 OR NOT((OLD.status='DRAFT' AND NEW.status IN ('REGRESSION_PASSED','REVOKED')) OR (OLD.status='REGRESSION_PASSED' AND NEW.status IN ('PUBLISHED','REVOKED')) OR (OLD.status='PUBLISHED' AND NEW.status='REVOKED')) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='PROMOTION_IMMUTABLE'; END IF;
 IF OLD.status<>'DRAFT' AND (NOT(NEW.regression_suite_id<=>OLD.regression_suite_id) OR NOT(NEW.regression_suite_version<=>OLD.regression_suite_version) OR NOT(NEW.regression_report_sha256<=>OLD.regression_report_sha256) OR NEW.total_cases<>OLD.total_cases OR NEW.passed_cases<>OLD.passed_cases OR NOT(NEW.regression_reviewer_id<=>OLD.regression_reviewer_id)) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='PROMOTION_PROOF_IMMUTABLE'; END IF;
END$$
CREATE TRIGGER trg_promotion_delete BEFORE DELETE ON ai_memory_promotion FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='PROMOTION_DELETE_FORBIDDEN'; END$$
CREATE TRIGGER trg_episode_revoke AFTER UPDATE ON ai_memory_episode FOR EACH ROW
BEGIN
 IF NEW.status='REVOKED' AND OLD.status<>'REVOKED' THEN UPDATE ai_memory_promotion SET status='REVOKED',revision=revision+1 WHERE tenant_id=NEW.tenant_id AND episode_id=NEW.id AND status<>'REVOKED'; END IF;
END$$
CREATE TRIGGER trg_episode_source_invalidation AFTER UPDATE ON ai_memory_source FOR EACH ROW
BEGIN
 IF NEW.grant_epoch>OLD.grant_epoch OR NEW.source_epoch>OLD.source_epoch OR NEW.deletion_epoch>OLD.deletion_epoch OR (OLD.retention_deadline IS NOT NULL AND (NEW.retention_deadline IS NULL OR NEW.retention_deadline<OLD.retention_deadline)) THEN
  UPDATE ai_memory_episode e SET e.status='REVOKED',e.revision=e.revision+1,e.encrypted_payload=NULL,e.nonce=NULL,e.auth_tag=NULL,e.content_hmac=NULL,e.shared_payload=NULL,e.shared_nonce=NULL,e.shared_tag=NULL,e.shared_hmac=NULL
   WHERE e.tenant_id=NEW.tenant_id AND e.status<>'REVOKED' AND EXISTS(SELECT 1 FROM ai_memory_dependency d WHERE d.tenant_id=e.tenant_id AND d.target_type='EPISODE' AND d.target_id=e.id AND d.source_id=NEW.id);
 END IF;
END$$
DELIMITER ;
