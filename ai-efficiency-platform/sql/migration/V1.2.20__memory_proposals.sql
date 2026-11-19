-- D25：只新增本模块候选/批次/来源机会锚，不激活开关，不修改既有迁移。
-- MySQL DDL隐式提交；仅独立授权环境执行；默认不开启自动生成/索引，不初始化外部账本。
SET SESSION lock_wait_timeout=5;
SET SESSION innodb_lock_wait_timeout=5;
CREATE TABLE ai_memory_proposal_batch (
 tenant_id VARBINARY(512) NOT NULL,task_id VARBINARY(512) NOT NULL,execution_id VARBINARY(512) NOT NULL,
 user_id VARBINARY(512) NOT NULL,domain VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 session_id VARBINARY(512) NOT NULL,request_id VARBINARY(512) NOT NULL,
 fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 policy_id VARBINARY(512) NOT NULL,policy_version_id VARBINARY(512) NOT NULL,actions_json JSON NOT NULL,
 recorded_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(tenant_id,task_id),UNIQUE KEY uk_proposal_batch_request(tenant_id,request_id),
 CONSTRAINT fk_proposal_batch_execution FOREIGN KEY(tenant_id,execution_id) REFERENCES ai_memory_packet(tenant_id,execution_id),
 CONSTRAINT fk_proposal_batch_policy FOREIGN KEY(tenant_id,policy_id,policy_version_id) REFERENCES ai_memory_policy_version(tenant_id,policy_id,version_id),
 CONSTRAINT ck_proposal_batch CHECK(domain IN ('operations','customer-service') AND OCTET_LENGTH(task_id)>0 AND OCTET_LENGTH(user_id)>0 AND OCTET_LENGTH(session_id)>0 AND REGEXP_LIKE(fingerprint,'^[0-9a-f]{64}$','c') AND JSON_TYPE(actions_json)='ARRAY' AND JSON_LENGTH(actions_json)<=16)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
CREATE TABLE ai_memory_proposal_source_claim (
 tenant_id VARBINARY(512) NOT NULL,source_id VARBINARY(512) NOT NULL,source_version VARBINARY(512) NOT NULL,task_id VARBINARY(512) NOT NULL,
 PRIMARY KEY(tenant_id,source_id,source_version),KEY ix_proposal_claim_task(tenant_id,task_id),
 CONSTRAINT fk_proposal_claim_source FOREIGN KEY(tenant_id,source_id) REFERENCES ai_memory_source(tenant_id,id),
 CONSTRAINT fk_proposal_claim_batch FOREIGN KEY(tenant_id,task_id) REFERENCES ai_memory_proposal_batch(tenant_id,task_id),
 CONSTRAINT ck_proposal_claim CHECK(OCTET_LENGTH(source_id)>0 AND OCTET_LENGTH(source_version)>0)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
CREATE TABLE ai_memory_proposal (
 tenant_id VARBINARY(512) NOT NULL,id VARBINARY(512) NOT NULL,item_id VARBINARY(512) NOT NULL,
 task_id VARBINARY(512) NOT NULL,execution_id VARBINARY(512) NOT NULL,user_id VARBINARY(512) NOT NULL,
 domain VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,top_level_agent_id VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 session_id VARBINARY(512) NOT NULL,field_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 action VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,status VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 revision BIGINT UNSIGNED NOT NULL DEFAULT 0,expected_item_revision BIGINT UNSIGNED NOT NULL,
 policy_id VARBINARY(512) NOT NULL,policy_version_id VARBINARY(512) NOT NULL,expires_at DATETIME(6) NOT NULL,
 source_message_ids_json JSON NOT NULL,dependencies_json JSON NOT NULL,
 key_version VARBINARY(128) NOT NULL,encrypted_payload BLOB NULL,nonce BINARY(12) NULL,auth_tag BINARY(16) NULL,content_hmac BINARY(32) NULL,
 decision_request_id VARBINARY(512) NULL,decision_actor_id VARBINARY(512) NULL,decision_action VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NULL,
 decision_expected_revision BIGINT UNSIGNED NOT NULL DEFAULT 0,decision_expected_item_revision BIGINT UNSIGNED NOT NULL DEFAULT 0,accepted_version_id VARBINARY(512) NULL,
 index_status VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'NOT_REQUESTED',
 pending_marker TINYINT GENERATED ALWAYS AS(CASE WHEN status='PENDING' THEN 1 ELSE NULL END) STORED,
 recorded_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(tenant_id,id),UNIQUE KEY uk_proposal_decision_request(tenant_id,decision_request_id),
 UNIQUE KEY uk_proposal_pending_value(tenant_id,item_id,content_hmac,pending_marker),
 KEY ix_proposal_owned(tenant_id,user_id,domain,session_id),KEY ix_proposal_batch(tenant_id,task_id),
 CONSTRAINT fk_proposal_item FOREIGN KEY(tenant_id,item_id) REFERENCES ai_memory_item(tenant_id,id),
 CONSTRAINT fk_proposal_batch FOREIGN KEY(tenant_id,task_id) REFERENCES ai_memory_proposal_batch(tenant_id,task_id),
 CONSTRAINT fk_proposal_policy FOREIGN KEY(tenant_id,policy_id,policy_version_id) REFERENCES ai_memory_policy_version(tenant_id,policy_id,version_id),
 CONSTRAINT fk_proposal_accepted_version FOREIGN KEY(tenant_id,item_id,accepted_version_id) REFERENCES ai_memory_version(tenant_id,item_id,id),
 CONSTRAINT ck_proposal_scope CHECK(domain IN ('operations','customer-service') AND top_level_agent_id=domain AND OCTET_LENGTH(user_id)>0 AND OCTET_LENGTH(session_id)>0 AND field_key IN ('response.language','response.detail_level','response.format')),
 CONSTRAINT ck_proposal_action CHECK(action IN ('ADD','REPLACE_CANDIDATE','CONFLICT_CANDIDATE')),
 CONSTRAINT ck_proposal_status CHECK(status IN ('PENDING','ACCEPTED','REJECTED','STALE','SUPPRESSED','EXPIRED') AND index_status='NOT_REQUESTED'),
 CONSTRAINT ck_proposal_sources CHECK(JSON_TYPE(source_message_ids_json)='ARRAY' AND JSON_LENGTH(source_message_ids_json) BETWEEN 1 AND 128 AND JSON_TYPE(dependencies_json)='ARRAY' AND JSON_LENGTH(dependencies_json) BETWEEN 1 AND 512),
 CONSTRAINT ck_proposal_body CHECK((encrypted_payload IS NULL AND nonce IS NULL AND auth_tag IS NULL AND content_hmac IS NULL AND status<>'PENDING') OR (encrypted_payload IS NOT NULL AND OCTET_LENGTH(encrypted_payload)<=512 AND nonce IS NOT NULL AND auth_tag IS NOT NULL AND content_hmac IS NOT NULL)),
 CONSTRAINT ck_proposal_decision CHECK((decision_request_id IS NULL AND decision_actor_id IS NULL AND decision_action IS NULL AND accepted_version_id IS NULL) OR (decision_request_id IS NOT NULL AND decision_actor_id IS NOT NULL AND ((status='ACCEPTED' AND decision_action='CONFIRM' AND accepted_version_id IS NOT NULL) OR (status='REJECTED' AND decision_action='REJECT' AND accepted_version_id IS NULL))))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
DELIMITER $$
CREATE TRIGGER trg_proposal_update BEFORE UPDATE ON ai_memory_proposal FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.item_id<=>OLD.item_id) OR NOT(NEW.task_id<=>OLD.task_id) OR NOT(NEW.execution_id<=>OLD.execution_id) OR NOT(NEW.user_id<=>OLD.user_id) OR NOT(NEW.domain<=>OLD.domain) OR NOT(NEW.top_level_agent_id<=>OLD.top_level_agent_id) OR NOT(NEW.session_id<=>OLD.session_id) OR NOT(NEW.field_key<=>OLD.field_key) OR NOT(NEW.action<=>OLD.action) OR NOT(NEW.expected_item_revision<=>OLD.expected_item_revision) OR NOT(NEW.policy_id<=>OLD.policy_id) OR NOT(NEW.policy_version_id<=>OLD.policy_version_id) OR NOT(NEW.expires_at<=>OLD.expires_at) OR NOT(NEW.source_message_ids_json<=>OLD.source_message_ids_json) OR NOT(NEW.dependencies_json<=>OLD.dependencies_json) OR NOT(NEW.key_version<=>OLD.key_version) OR NEW.index_status<>'NOT_REQUESTED' OR NEW.revision<>OLD.revision+1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='PROPOSAL_IMMUTABLE'; END IF;
 IF OLD.status='PENDING' THEN
  IF NEW.status NOT IN ('ACCEPTED','REJECTED','STALE','SUPPRESSED','EXPIRED') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='PROPOSAL_STATE_INVALID'; END IF;
 ELSEIF NEW.status<>OLD.status OR NOT(NEW.decision_request_id<=>OLD.decision_request_id) OR NOT(NEW.decision_actor_id<=>OLD.decision_actor_id) OR NOT(NEW.decision_action<=>OLD.decision_action) OR NOT(NEW.accepted_version_id<=>OLD.accepted_version_id) OR NEW.decision_expected_revision<>OLD.decision_expected_revision OR NEW.decision_expected_item_revision<>OLD.decision_expected_item_revision OR NEW.encrypted_payload IS NOT NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='PROPOSAL_TERMINAL_IMMUTABLE';
 END IF;
 IF NEW.encrypted_payload IS NOT NULL AND (NOT(NEW.encrypted_payload<=>OLD.encrypted_payload) OR NOT(NEW.nonce<=>OLD.nonce) OR NOT(NEW.auth_tag<=>OLD.auth_tag) OR NOT(NEW.content_hmac<=>OLD.content_hmac)) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='PROPOSAL_BODY_IMMUTABLE'; END IF;
END$$
CREATE TRIGGER trg_proposal_delete BEFORE DELETE ON ai_memory_proposal FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='PROPOSAL_DELETE_FORBIDDEN'; END$$
CREATE TRIGGER trg_proposal_claim_update BEFORE UPDATE ON ai_memory_proposal_source_claim FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='PROPOSAL_SOURCE_OPPORTUNITY_IMMUTABLE'; END$$
CREATE TRIGGER trg_proposal_claim_delete BEFORE DELETE ON ai_memory_proposal_source_claim FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='PROPOSAL_SOURCE_OPPORTUNITY_IMMUTABLE'; END$$
CREATE TRIGGER trg_proposal_batch_update BEFORE UPDATE ON ai_memory_proposal_batch FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.task_id<=>OLD.task_id) OR NOT(NEW.execution_id<=>OLD.execution_id) OR NOT(NEW.user_id<=>OLD.user_id) OR NOT(NEW.domain<=>OLD.domain) OR NOT(NEW.session_id<=>OLD.session_id) OR NOT(NEW.request_id<=>OLD.request_id) OR NOT(NEW.fingerprint<=>OLD.fingerprint) OR NOT(NEW.policy_id<=>OLD.policy_id) OR NOT(NEW.policy_version_id<=>OLD.policy_version_id) OR JSON_LENGTH(OLD.actions_json)<>0 OR JSON_LENGTH(NEW.actions_json)=0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='PROPOSAL_BATCH_IMMUTABLE'; END IF;
END$$
CREATE TRIGGER trg_proposal_batch_delete BEFORE DELETE ON ai_memory_proposal_batch FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='PROPOSAL_TASK_OPPORTUNITY_IMMUTABLE'; END$$
CREATE TRIGGER trg_proposal_source_invalidation AFTER UPDATE ON ai_memory_source FOR EACH ROW
BEGIN
 IF NEW.grant_epoch>OLD.grant_epoch OR NEW.source_epoch>OLD.source_epoch OR NEW.deletion_epoch>OLD.deletion_epoch OR (OLD.retention_deadline IS NOT NULL AND (NEW.retention_deadline IS NULL OR NEW.retention_deadline<OLD.retention_deadline)) THEN
  UPDATE ai_memory_proposal p SET p.status=CASE WHEN p.status='PENDING' THEN 'STALE' ELSE p.status END,p.revision=p.revision+1,p.encrypted_payload=NULL,p.nonce=NULL,p.auth_tag=NULL,p.content_hmac=NULL
   WHERE p.tenant_id=NEW.tenant_id AND p.encrypted_payload IS NOT NULL AND EXISTS(SELECT 1 FROM ai_memory_dependency d WHERE d.tenant_id=p.tenant_id AND d.target_type='PROPOSAL' AND d.target_id=p.id AND d.source_id=NEW.id);
 END IF;
END$$
CREATE TRIGGER trg_proposal_suppression_insert AFTER INSERT ON ai_memory_suppression FOR EACH ROW
BEGIN
 IF NEW.active THEN
  UPDATE ai_memory_proposal p SET p.status=CASE WHEN p.status='PENDING' THEN 'SUPPRESSED' ELSE p.status END,p.revision=p.revision+1,p.encrypted_payload=NULL,p.nonce=NULL,p.auth_tag=NULL,p.content_hmac=NULL
   WHERE p.tenant_id=NEW.tenant_id AND p.encrypted_payload IS NOT NULL AND
    ((NEW.suppression_kind='FIELD' AND NEW.subject_type='USER' AND NEW.subject_id=p.user_id AND NEW.domain=p.domain AND NEW.scope_type='USER_PRIVATE' AND NEW.purpose='assistant_response' AND NEW.field_key=p.field_key AND EXISTS(SELECT 1 FROM ai_memory_item i WHERE i.tenant_id=p.tenant_id AND i.id=p.item_id AND i.scope_id=NEW.scope_id))
     OR (NEW.suppression_kind='SOURCE' AND EXISTS(SELECT 1 FROM ai_memory_dependency d WHERE d.tenant_id=p.tenant_id AND d.target_type='PROPOSAL' AND d.target_id=p.id AND d.source_id=NEW.source_id)));
 END IF;
END$$
CREATE TRIGGER trg_proposal_suppression_update AFTER UPDATE ON ai_memory_suppression FOR EACH ROW
BEGIN
 IF NEW.active AND (NOT OLD.active OR NEW.epoch>OLD.epoch) THEN
  UPDATE ai_memory_proposal p SET p.status=CASE WHEN p.status='PENDING' THEN 'SUPPRESSED' ELSE p.status END,p.revision=p.revision+1,p.encrypted_payload=NULL,p.nonce=NULL,p.auth_tag=NULL,p.content_hmac=NULL
   WHERE p.tenant_id=NEW.tenant_id AND p.encrypted_payload IS NOT NULL AND
    ((NEW.suppression_kind='FIELD' AND NEW.subject_type='USER' AND NEW.subject_id=p.user_id AND NEW.domain=p.domain AND NEW.scope_type='USER_PRIVATE' AND NEW.purpose='assistant_response' AND NEW.field_key=p.field_key AND EXISTS(SELECT 1 FROM ai_memory_item i WHERE i.tenant_id=p.tenant_id AND i.id=p.item_id AND i.scope_id=NEW.scope_id))
     OR (NEW.suppression_kind='SOURCE' AND EXISTS(SELECT 1 FROM ai_memory_dependency d WHERE d.tenant_id=p.tenant_id AND d.target_type='PROPOSAL' AND d.target_id=p.id AND d.source_id=NEW.source_id)));
 END IF;
END$$
DELIMITER ;
