-- aiep-biz-aihub；新增且仅新增12个记忆元数据/加密版本对象，不修改既有业务表。
-- 前置：V1.2.16__precheck_agent_memory.sql逐项审阅、独立空MySQL演练通过、共享DDL单独授权。
-- 不回填历史消息，不启用长期召回/模型/索引；所有权限策略默认关闭。
-- 人工回滚：R__V1.2.16__agent_memory_core.sql；仅新建空库可破坏性回滚，生产含数据时停止审阅。

CREATE TABLE ai_memory_session_binding (
 tenant_id VARBINARY(512) NOT NULL, id VARBINARY(512) NOT NULL,
 user_id VARBINARY(512) NOT NULL, domain VARBINARY(32) NOT NULL,
 top_level_agent_id VARBINARY(32) NOT NULL,
 session_id VARBINARY(512) NOT NULL, session_kind VARBINARY(16) NOT NULL DEFAULT 'CONVERSATION',
 original_object_type VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 original_object_id VARBINARY(512) NOT NULL, revision BIGINT UNSIGNED NOT NULL DEFAULT 0,
 grant_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0, source_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0,
 deletion_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0, created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(tenant_id,id), UNIQUE KEY uk_memory_session(tenant_id,user_id,session_id),
 CONSTRAINT ck_memory_binding_kind CHECK(session_kind='CONVERSATION'),
 CONSTRAINT ck_memory_binding_catalog CHECK(domain IN ('operations','customer-service') AND domain=top_level_agent_id),
 CONSTRAINT ck_memory_binding_ids CHECK(OCTET_LENGTH(tenant_id)>0 AND OCTET_LENGTH(user_id)>0 AND OCTET_LENGTH(session_id)>0)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE ai_memory_policy (
 tenant_id VARBINARY(512) NOT NULL, id VARBINARY(512) NOT NULL,
 domain VARBINARY(32) NOT NULL,
 current_version_id VARBINARY(512) NULL, enabled BOOLEAN NOT NULL DEFAULT FALSE,
 revision BIGINT UNSIGNED NOT NULL DEFAULT 0,
 PRIMARY KEY(tenant_id,id), CONSTRAINT ck_memory_policy_domain CHECK(domain IN ('operations','customer-service','hr'))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE ai_memory_policy_version (
 tenant_id VARBINARY(512) NOT NULL, policy_id VARBINARY(512) NOT NULL, version_id VARBINARY(512) NOT NULL,
 policy_json JSON NOT NULL, content_hmac BINARY(32) NOT NULL,
 schema_version VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'memory-policy/1',
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(tenant_id,policy_id,version_id),
 CONSTRAINT fk_memory_policy_version FOREIGN KEY(tenant_id,policy_id) REFERENCES ai_memory_policy(tenant_id,id),
 CONSTRAINT ck_memory_policy_json CHECK(JSON_TYPE(policy_json)='OBJECT')
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
ALTER TABLE ai_memory_policy ADD CONSTRAINT fk_memory_policy_current FOREIGN KEY(tenant_id,id,current_version_id)
 REFERENCES ai_memory_policy_version(tenant_id,policy_id,version_id);

CREATE TABLE ai_memory_item (
 tenant_id VARBINARY(512) NOT NULL, id VARBINARY(512) NOT NULL,
 subject_type VARBINARY(32) NOT NULL DEFAULT 'USER',
 subject_id VARBINARY(512) NOT NULL, owner_id VARBINARY(512) NOT NULL,
 domain VARBINARY(32) NOT NULL,
 origin_top_agent_id VARBINARY(32) NOT NULL,
 scope_type VARBINARY(32) NOT NULL DEFAULT 'USER_PRIVATE', scope_id VARBINARY(1024) NOT NULL,
 purpose VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'assistant_response',
 field_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 memory_layer VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'LONG_TERM',
 kind VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'PREFERENCE',
 lifecycle VARBINARY(16) NOT NULL DEFAULT 'LIVE',
 revision BIGINT UNSIGNED NOT NULL DEFAULT 0, current_version_id VARBINARY(512) NULL,
 grant_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0, source_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0,
 deletion_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0,
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uk_memory_item_logical(tenant_id,subject_type,subject_id,domain,scope_type,scope_id,purpose,field_key),
 CONSTRAINT ck_memory_item_ids CHECK(OCTET_LENGTH(tenant_id)>0 AND OCTET_LENGTH(id)>0 AND OCTET_LENGTH(subject_id)>0 AND OCTET_LENGTH(owner_id)>0 AND OCTET_LENGTH(scope_id)>0),
 CONSTRAINT ck_memory_item_catalog CHECK(domain IN ('operations','customer-service','hr') AND origin_top_agent_id IN ('operations','customer-service','hr')),
 CONSTRAINT ck_memory_item_scope_type CHECK(scope_type IN ('RUN','SESSION','USER_PRIVATE','PROJECT','DEPARTMENT','ORGANIZATION')),
 CONSTRAINT ck_memory_item_private CHECK(scope_type<>'USER_PRIVATE' OR (subject_type='USER' AND domain=origin_top_agent_id AND scope_id=CONCAT(_binary'up1:',UNHEX(LPAD(HEX(OCTET_LENGTH(subject_id)),8,'0')),subject_id,origin_top_agent_id))),
 CONSTRAINT ck_memory_machine_field CHECK(REGEXP_LIKE(purpose,'^[a-z][a-z0-9_.-]{0,63}$','c') AND REGEXP_LIKE(field_key,'^[a-z][a-z0-9_.-]{0,127}$','c')),
 CONSTRAINT ck_memory_item_state CHECK(lifecycle IN ('LIVE','REVOKED','EXPIRED','DELETE_PENDING','DELETED')),
 CONSTRAINT ck_memory_deleted_pointer CHECK(lifecycle<>'DELETED' OR current_version_id IS NULL)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE ai_memory_decision (
 tenant_id VARBINARY(512) NOT NULL, id VARBINARY(512) NOT NULL, item_id VARBINARY(512) NOT NULL,
 target_version_id VARBINARY(512) NULL, actor_id VARBINARY(512) NOT NULL,
 actor_kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'USER',
 decision_type VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL, request_id VARBINARY(512) NOT NULL,
 expected_revision BIGINT UNSIGNED NOT NULL, resulting_revision BIGINT UNSIGNED NOT NULL,
 expected_suppression_revision BIGINT UNSIGNED NULL,
 recorded_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(tenant_id,id), UNIQUE KEY uk_memory_decision_request(tenant_id,request_id),
 CONSTRAINT fk_memory_decision_item FOREIGN KEY(tenant_id,item_id) REFERENCES ai_memory_item(tenant_id,id)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE ai_memory_version (
 tenant_id VARBINARY(512) NOT NULL, item_id VARBINARY(512) NOT NULL, id VARBINARY(512) NOT NULL,
 status VARBINARY(16) NOT NULL,
 active_marker TINYINT GENERATED ALWAYS AS (CASE WHEN status='ACTIVE' THEN 1 ELSE NULL END) STORED,
 encrypted_payload LONGBLOB NULL, key_version VARBINARY(128) NOT NULL,
 cipher_algorithm VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'AES-256-GCM',
 payload_schema VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'memory-value/1',
 nonce VARBINARY(32) NULL, auth_tag VARBINARY(32) NULL, content_hmac BINARY(32) NULL,
 aad_format VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'memory-aad/1',
 aad_tenant_id VARBINARY(512) NOT NULL, aad_item_id VARBINARY(512) NOT NULL,
 aad_version_id VARBINARY(512) NOT NULL, aad_key_version VARBINARY(128) NOT NULL,
 policy_id VARBINARY(512) NULL, policy_version_id VARBINARY(512) NULL, decision_id VARBINARY(512) NULL,
 supersedes_version_id VARBINARY(512) NULL, input_manifest_id VARBINARY(512) NULL,
 observed_at DATETIME(6) NULL, valid_from DATETIME(6) NULL, valid_to DATETIME(6) NULL, expires_at DATETIME(6) NULL,
 grant_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0, source_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0,
 deletion_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0, scrubbed_at DATETIME(6) NULL,
 recorded_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(tenant_id,id), UNIQUE KEY uk_memory_version_owner(tenant_id,item_id,id),
 UNIQUE KEY uk_memory_one_active(tenant_id,item_id,active_marker),
 CONSTRAINT fk_memory_version_item FOREIGN KEY(tenant_id,item_id) REFERENCES ai_memory_item(tenant_id,id),
 CONSTRAINT fk_memory_version_decision FOREIGN KEY(tenant_id,decision_id) REFERENCES ai_memory_decision(tenant_id,id),
 CONSTRAINT fk_memory_version_policy FOREIGN KEY(tenant_id,policy_id,policy_version_id) REFERENCES ai_memory_policy_version(tenant_id,policy_id,version_id),
 CONSTRAINT ck_memory_version_status CHECK(status IN ('ACTIVE','SUPERSEDED','CONFLICTED','REVOKED','EXPIRED','DELETED')),
 CONSTRAINT ck_memory_version_aad CHECK(aad_tenant_id=tenant_id AND aad_item_id=item_id AND aad_version_id=id AND aad_key_version=key_version),
 CONSTRAINT ck_memory_version_body CHECK((status='DELETED' AND encrypted_payload IS NULL AND nonce IS NULL AND auth_tag IS NULL AND content_hmac IS NULL AND scrubbed_at IS NOT NULL) OR (status<>'DELETED' AND encrypted_payload IS NOT NULL AND nonce IS NOT NULL AND auth_tag IS NOT NULL AND OCTET_LENGTH(nonce)=12 AND OCTET_LENGTH(auth_tag)=16 AND content_hmac IS NOT NULL AND scrubbed_at IS NULL)),
 CONSTRAINT ck_memory_version_times CHECK(valid_to IS NULL OR valid_from IS NULL OR valid_to>=valid_from)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
ALTER TABLE ai_memory_item ADD CONSTRAINT fk_memory_item_current FOREIGN KEY(tenant_id,id,current_version_id)
 REFERENCES ai_memory_version(tenant_id,item_id,id);

CREATE TABLE ai_memory_source (
 tenant_id VARBINARY(512) NOT NULL, id VARBINARY(512) NOT NULL,
 source_type VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 source_object_ref VARBINARY(512) NOT NULL, source_version VARBINARY(512) NOT NULL,
 source_event_id VARBINARY(512) NULL, evidence_spans JSON NULL, trust_level VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'UNVERIFIED',
 grant_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0, source_epoch BIGINT UNSIGNED NOT NULL DEFAULT 1,
 deletion_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0, retention_deadline DATETIME(6) NULL,
 PRIMARY KEY(tenant_id,id), UNIQUE KEY uk_memory_source_ref(tenant_id,source_type,source_object_ref,source_version)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE ai_memory_dependency (
 tenant_id VARBINARY(512) NOT NULL, source_id VARBINARY(512) NOT NULL,
 target_type VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 target_id VARBINARY(512) NOT NULL, target_version VARBINARY(512) NOT NULL,
 execution_id VARBINARY(512) NULL, root_thread_ref VARBINARY(512) NULL, child_thread_ref VARBINARY(512) NULL, checkpoint_namespace VARBINARY(512) NULL,
 grant_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0, source_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0, deletion_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0,
 PRIMARY KEY(tenant_id,source_id,target_type,target_id,target_version),
 KEY ix_memory_dependency_target(tenant_id,target_type,target_id,target_version,source_id),
 CONSTRAINT fk_memory_dependency_source FOREIGN KEY(tenant_id,source_id) REFERENCES ai_memory_source(tenant_id,id)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE ai_memory_suppression (
 tenant_id VARBINARY(512) NOT NULL, id VARBINARY(512) NOT NULL,
 subject_type VARBINARY(32) NOT NULL DEFAULT 'USER', subject_id VARBINARY(512) NOT NULL,
 domain VARBINARY(32) NOT NULL,
 scope_type VARBINARY(32) NOT NULL, scope_id VARBINARY(1024) NOT NULL,
 purpose VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT '', field_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT '',
 suppression_kind VARBINARY(16) NOT NULL DEFAULT 'FIELD',
 source_id VARBINARY(512) NOT NULL DEFAULT '', source_version VARBINARY(512) NOT NULL DEFAULT '',
 epoch BIGINT UNSIGNED NOT NULL DEFAULT 1, active BOOLEAN NOT NULL DEFAULT TRUE,
 field_marker TINYINT GENERATED ALWAYS AS (CASE WHEN suppression_kind='FIELD' THEN 1 ELSE NULL END) STORED,
 source_marker TINYINT GENERATED ALWAYS AS (CASE WHEN suppression_kind='SOURCE' THEN 1 ELSE NULL END) STORED,
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uk_memory_suppression_field(tenant_id,subject_type,subject_id,domain,scope_type,scope_id,purpose,field_key,field_marker),
 UNIQUE KEY uk_memory_suppression_source(tenant_id,source_id,source_version,source_marker),
 KEY ix_memory_suppression_source(tenant_id,source_id,source_version),
 CONSTRAINT ck_memory_suppression_domain CHECK(domain IN ('operations','customer-service','hr')),
 CONSTRAINT ck_memory_suppression_scope_type CHECK(scope_type IN ('RUN','SESSION','USER_PRIVATE','PROJECT','DEPARTMENT','ORGANIZATION')),
 CONSTRAINT ck_memory_suppression_epoch CHECK(epoch>0),
 CONSTRAINT ck_memory_suppression_scope CHECK(OCTET_LENGTH(scope_id)>0 AND OCTET_LENGTH(subject_id)>0),
 CONSTRAINT ck_memory_suppression_kind CHECK((suppression_kind='FIELD' AND field_key<>'' AND source_id='' AND source_version='') OR (suppression_kind='SOURCE' AND source_id<>'' AND source_version<>''))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE ai_memory_outbox (
 tenant_id VARBINARY(512) NOT NULL, event_id VARBINARY(512) NOT NULL,
 aggregate_id VARBINARY(512) NOT NULL, version_id VARBINARY(512) NOT NULL DEFAULT '',
 event_type VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 deletion_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0, generation BIGINT UNSIGNED NOT NULL DEFAULT 0,
 payload JSON NULL, status VARBINARY(16) NOT NULL DEFAULT 'QUEUED',
 revision BIGINT UNSIGNED NOT NULL DEFAULT 0, attempts INT UNSIGNED NOT NULL DEFAULT 0,
 lease_until DATETIME(6) NULL, receipt_ref VARBINARY(512) NULL,
 PRIMARY KEY(tenant_id,event_id), UNIQUE KEY uk_memory_outbox_event(tenant_id,aggregate_id,version_id,event_type,deletion_epoch,generation),
 CONSTRAINT ck_memory_outbox_status CHECK(status IN ('QUEUED','CLAIMED','SUCCEEDED','BLOCKED'))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE ai_memory_deletion_job (
 tenant_id VARBINARY(512) NOT NULL, id VARBINARY(512) NOT NULL, item_id VARBINARY(512) NOT NULL,
 deletion_epoch BIGINT UNSIGNED NOT NULL, request_id VARBINARY(512) NULL, requested_by VARBINARY(512) NULL,
 status VARBINARY(32) NOT NULL DEFAULT 'QUEUED',
 required_targets INT UNSIGNED NOT NULL DEFAULT 0, completed_targets INT UNSIGNED NOT NULL DEFAULT 0,
 revision BIGINT UNSIGNED NOT NULL DEFAULT 0, attempts INT UNSIGNED NOT NULL DEFAULT 0,
 lease_until DATETIME(6) NULL, deadline DATETIME(6) NULL, receipts JSON NULL,
 PRIMARY KEY(tenant_id,id), UNIQUE KEY uk_memory_deletion_epoch(tenant_id,item_id,deletion_epoch),
 CONSTRAINT fk_memory_deletion_item FOREIGN KEY(tenant_id,item_id) REFERENCES ai_memory_item(tenant_id,id),
 CONSTRAINT ck_memory_deletion_state CHECK(status IN ('QUEUED','CLAIMED','RUNNING','SUCCEEDED','WAITING_BUDGET','BLOCKED_SOURCE','RETRYABLE_FAILED','BLOCKED','FAILED','CANCELLED','EXPIRED')),
 CONSTRAINT ck_memory_deletion_progress CHECK(completed_targets<=required_targets AND (status<>'SUCCEEDED' OR completed_targets=required_targets))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

CREATE TABLE ai_memory_tombstone (
 tenant_id VARBINARY(512) NOT NULL, target_type VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 target_id VARBINARY(512) NOT NULL,
 deletion_epoch BIGINT UNSIGNED NOT NULL, grant_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0, source_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0,
 recorded_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(tenant_id,target_type,target_id)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;

DELIMITER $$
CREATE TRIGGER trg_memory_item_insert BEFORE INSERT ON ai_memory_item FOR EACH ROW
BEGIN
 IF NEW.current_version_id IS NOT NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_CURRENT_REQUIRES_EXISTING_ACTIVE'; END IF;
END$$
CREATE TRIGGER trg_memory_item_update BEFORE UPDATE ON ai_memory_item FOR EACH ROW
BEGIN
 DECLARE active_count INT DEFAULT 0;
 DECLARE reauth_count INT DEFAULT 0;
 DECLARE expected_suppression BIGINT UNSIGNED DEFAULT NULL;
 DECLARE field_count INT DEFAULT 0;
 DECLARE field_epoch BIGINT UNSIGNED DEFAULT NULL;
 DECLARE field_active BOOLEAN DEFAULT NULL;
 DECLARE source_count INT DEFAULT 0;
 DECLARE blocked_source_count INT DEFAULT 0;
 DECLARE unscrubbed_count INT DEFAULT 0;
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.subject_type<=>OLD.subject_type) OR NOT(NEW.subject_id<=>OLD.subject_id) OR NOT(NEW.domain<=>OLD.domain) OR NOT(NEW.origin_top_agent_id<=>OLD.origin_top_agent_id) OR NOT(NEW.scope_type<=>OLD.scope_type) OR NOT(NEW.scope_id<=>OLD.scope_id) OR NOT(NEW.purpose<=>OLD.purpose) OR NOT(NEW.field_key<=>OLD.field_key) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_LOGICAL_KEY_IMMUTABLE'; END IF;
 IF NEW.revision<OLD.revision OR NEW.grant_epoch<OLD.grant_epoch OR NEW.source_epoch<OLD.source_epoch OR NEW.deletion_epoch<OLD.deletion_epoch THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_ITEM_EPOCH_REGRESSION'; END IF;
 -- 保留逻辑anchor；仅显式人类新版本重新授权可以离开DELETED，旧版本终态不变。
 IF OLD.lifecycle='DELETED' AND NEW.lifecycle<>'DELETED' THEN
  IF NEW.lifecycle<>'LIVE' OR NEW.current_version_id IS NULL OR NEW.revision<>OLD.revision+1 OR NEW.grant_epoch<=OLD.grant_epoch OR NOT(NEW.owner_id<=>OLD.owner_id) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REAUTHORIZE_REQUIRED'; END IF;
  SELECT COUNT(*),MAX(d.expected_suppression_revision) INTO reauth_count,expected_suppression
   FROM ai_memory_version v JOIN ai_memory_decision d ON d.tenant_id=v.tenant_id AND d.id=v.decision_id
   WHERE v.tenant_id=NEW.tenant_id AND v.item_id=NEW.id AND v.id=NEW.current_version_id AND v.status='ACTIVE'
    AND d.item_id=NEW.id AND d.target_version_id=v.id AND d.actor_id=OLD.owner_id
    AND CAST(d.actor_kind AS BINARY)=_binary'USER' AND CAST(d.decision_type AS BINARY)=_binary'REAUTHORIZE'
    AND d.expected_revision=OLD.revision AND d.resulting_revision=NEW.revision AND d.expected_suppression_revision IS NOT NULL
    AND v.grant_epoch=NEW.grant_epoch AND v.source_epoch=NEW.source_epoch AND v.deletion_epoch=NEW.deletion_epoch FOR UPDATE;
  IF reauth_count<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REAUTHORIZE_REQUIRED'; END IF;
  SELECT COUNT(*),MAX(epoch),MAX(active) INTO field_count,field_epoch,field_active FROM ai_memory_suppression
   WHERE tenant_id=NEW.tenant_id AND subject_type=NEW.subject_type AND subject_id=NEW.subject_id AND domain=NEW.domain
    AND scope_type=NEW.scope_type AND scope_id=NEW.scope_id AND purpose=NEW.purpose AND field_key=NEW.field_key AND suppression_kind='FIELD' FOR UPDATE;
  -- 0只表示完整逻辑字段从未有规则；存在规则必须按原epoch显式解除，不可隐式跳过。
  IF (expected_suppression=0 AND field_count<>0) OR (expected_suppression>0 AND (field_count<>1 OR field_active<>FALSE OR field_epoch<>expected_suppression+1)) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REAUTHORIZE_SUPPRESSION_MISMATCH'; END IF;
  -- 对本新版本实际依赖的source先锁锚点；仍active的源抑制不能被字段重记一并解除。
  SELECT COUNT(*) INTO source_count FROM ai_memory_source src JOIN ai_memory_dependency dep ON dep.tenant_id=src.tenant_id AND dep.source_id=src.id
   WHERE dep.tenant_id=NEW.tenant_id AND dep.target_type='MEMORY_VERSION' AND dep.target_id=NEW.id AND dep.target_version=NEW.current_version_id FOR UPDATE;
  SELECT COUNT(*) INTO blocked_source_count FROM ai_memory_suppression sup JOIN ai_memory_source src ON src.tenant_id=sup.tenant_id AND src.id=sup.source_id AND src.source_version=sup.source_version
   JOIN ai_memory_dependency dep ON dep.tenant_id=src.tenant_id AND dep.source_id=src.id
   WHERE dep.tenant_id=NEW.tenant_id AND dep.target_type='MEMORY_VERSION' AND dep.target_id=NEW.id AND dep.target_version=NEW.current_version_id AND sup.suppression_kind='SOURCE' AND sup.active=TRUE FOR UPDATE;
  IF blocked_source_count<>0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REAUTHORIZE_SOURCE_SUPPRESSED'; END IF;
  SELECT COUNT(*) INTO unscrubbed_count FROM ai_memory_version WHERE tenant_id=NEW.tenant_id AND item_id=NEW.id AND id<>NEW.current_version_id
   AND (status<>'DELETED' OR encrypted_payload IS NOT NULL OR nonce IS NOT NULL OR auth_tag IS NOT NULL OR content_hmac IS NOT NULL OR scrubbed_at IS NULL) FOR UPDATE;
  IF unscrubbed_count<>0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REAUTHORIZE_DELETE_INCOMPLETE'; END IF;
 END IF;
 IF NEW.current_version_id IS NOT NULL THEN
  SELECT COUNT(*) INTO active_count FROM ai_memory_version WHERE tenant_id=NEW.tenant_id AND item_id=NEW.id AND id=NEW.current_version_id AND status='ACTIVE' FOR UPDATE;
  IF active_count<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_CURRENT_NOT_ACTIVE'; END IF;
 END IF;
END$$
CREATE TRIGGER trg_memory_version_update BEFORE UPDATE ON ai_memory_version FOR EACH ROW
BEGIN
 DECLARE pointed VARBINARY(512);
 DECLARE scrub_authorized INT DEFAULT 0;
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.item_id<=>OLD.item_id) OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.key_version<=>OLD.key_version) OR NOT(NEW.aad_tenant_id<=>OLD.aad_tenant_id) OR NOT(NEW.aad_item_id<=>OLD.aad_item_id) OR NOT(NEW.aad_version_id<=>OLD.aad_version_id) OR NOT(NEW.aad_key_version<=>OLD.aad_key_version) OR NOT(NEW.aad_format<=>OLD.aad_format) OR NOT(NEW.cipher_algorithm<=>OLD.cipher_algorithm) OR NOT(NEW.payload_schema<=>OLD.payload_schema) OR NOT(NEW.policy_id<=>OLD.policy_id) OR NOT(NEW.policy_version_id<=>OLD.policy_version_id) OR NOT(NEW.decision_id<=>OLD.decision_id) OR NOT(NEW.supersedes_version_id<=>OLD.supersedes_version_id) OR NOT(NEW.input_manifest_id<=>OLD.input_manifest_id) OR NOT(NEW.observed_at<=>OLD.observed_at) OR NOT(NEW.valid_from<=>OLD.valid_from) OR NOT(NEW.valid_to<=>OLD.valid_to) OR NOT(NEW.expires_at<=>OLD.expires_at) OR NOT(NEW.recorded_at<=>OLD.recorded_at) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_VERSION_IMMUTABLE'; END IF;
 IF NEW.grant_epoch<OLD.grant_epoch OR NEW.source_epoch<OLD.source_epoch OR NEW.deletion_epoch<OLD.deletion_epoch OR (OLD.status='DELETED' AND NEW.status<>'DELETED') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_VERSION_EPOCH_REGRESSION'; END IF;
 IF OLD.status<>'ACTIVE' AND NEW.status='ACTIVE' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_VERSION_REACTIVATION_FORBIDDEN'; END IF;
 IF OLD.status='ACTIVE' AND NEW.status<>'ACTIVE' THEN
  SELECT current_version_id INTO pointed FROM ai_memory_item WHERE tenant_id=OLD.tenant_id AND id=OLD.item_id FOR UPDATE;
  IF pointed<=>OLD.id THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_VERSION_STILL_CURRENT'; END IF;
 END IF;
 IF NOT(NEW.encrypted_payload<=>OLD.encrypted_payload) OR NOT(NEW.nonce<=>OLD.nonce) OR NOT(NEW.auth_tag<=>OLD.auth_tag) OR NOT(NEW.content_hmac<=>OLD.content_hmac) OR NOT(NEW.scrubbed_at<=>OLD.scrubbed_at) THEN
  SELECT COUNT(*) INTO scrub_authorized FROM ai_memory_deletion_job WHERE tenant_id=OLD.tenant_id AND item_id=OLD.item_id AND deletion_epoch=NEW.deletion_epoch AND status='SUCCEEDED' AND required_targets=completed_targets FOR UPDATE;
  IF OLD.status='DELETED' OR NEW.status<>'DELETED' OR NEW.deletion_epoch=0 OR NEW.encrypted_payload IS NOT NULL OR NEW.nonce IS NOT NULL OR NEW.auth_tag IS NOT NULL OR NEW.content_hmac IS NOT NULL OR NEW.scrubbed_at IS NULL OR scrub_authorized<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_BODY_OVERWRITE_FORBIDDEN'; END IF;
 END IF;
END$$
CREATE TRIGGER trg_memory_version_delete BEFORE DELETE ON ai_memory_version FOR EACH ROW
BEGIN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_VERSION_DELETE_FORBIDDEN';
END$$
CREATE TRIGGER trg_memory_policy_version_update BEFORE UPDATE ON ai_memory_policy_version FOR EACH ROW
BEGIN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_POLICY_VERSION_IMMUTABLE';
END$$
CREATE TRIGGER trg_memory_policy_version_delete BEFORE DELETE ON ai_memory_policy_version FOR EACH ROW
BEGIN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_POLICY_VERSION_DELETE_FORBIDDEN';
END$$
CREATE TRIGGER trg_memory_source_update BEFORE UPDATE ON ai_memory_source FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.source_type<=>OLD.source_type) OR NOT(NEW.source_object_ref<=>OLD.source_object_ref) OR NOT(NEW.source_version<=>OLD.source_version) OR NEW.grant_epoch<OLD.grant_epoch OR NEW.source_epoch<OLD.source_epoch OR NEW.deletion_epoch<OLD.deletion_epoch THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_SOURCE_REGRESSION'; END IF;
END$$
CREATE TRIGGER trg_memory_tombstone_update BEFORE UPDATE ON ai_memory_tombstone FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.target_type<=>OLD.target_type) OR NOT(NEW.target_id<=>OLD.target_id) OR NEW.deletion_epoch<OLD.deletion_epoch OR NEW.grant_epoch<OLD.grant_epoch OR NEW.source_epoch<OLD.source_epoch THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_TOMBSTONE_REGRESSION'; END IF;
END$$
CREATE TRIGGER trg_memory_tombstone_delete BEFORE DELETE ON ai_memory_tombstone FOR EACH ROW
BEGIN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_TOMBSTONE_DELETE_FORBIDDEN';
END$$
-- 与item重新授权共用锚点锁；规则不存在时也不依赖隔离级别的gap lock。
CREATE TRIGGER trg_memory_suppression_insert BEFORE INSERT ON ai_memory_suppression FOR EACH ROW
BEGIN
 DECLARE anchor VARBINARY(512) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET anchor=NULL;
 IF NEW.suppression_kind='FIELD' THEN
  SELECT id INTO anchor FROM ai_memory_item WHERE tenant_id=NEW.tenant_id AND subject_type=NEW.subject_type AND subject_id=NEW.subject_id AND domain=NEW.domain AND scope_type=NEW.scope_type AND scope_id=NEW.scope_id AND purpose=NEW.purpose AND field_key=NEW.field_key FOR UPDATE;
 ELSEIF NEW.suppression_kind='SOURCE' THEN
  SELECT id INTO anchor FROM ai_memory_source WHERE tenant_id=NEW.tenant_id AND id=NEW.source_id FOR UPDATE;
 END IF;
END$$
CREATE TRIGGER trg_memory_suppression_update BEFORE UPDATE ON ai_memory_suppression FOR EACH ROW
BEGIN
 DECLARE anchor VARBINARY(512) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET anchor=NULL;
 IF NEW.epoch<OLD.epoch OR NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.subject_type<=>OLD.subject_type) OR NOT(NEW.subject_id<=>OLD.subject_id) OR NOT(NEW.domain<=>OLD.domain) OR NOT(NEW.scope_type<=>OLD.scope_type) OR NOT(NEW.scope_id<=>OLD.scope_id) OR NOT(NEW.purpose<=>OLD.purpose) OR NOT(NEW.field_key<=>OLD.field_key) OR NOT(NEW.source_id<=>OLD.source_id) OR NOT(NEW.source_version<=>OLD.source_version) OR NOT(NEW.suppression_kind<=>OLD.suppression_kind) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_SUPPRESSION_REGRESSION'; END IF;
 IF OLD.suppression_kind='FIELD' THEN
  SELECT id INTO anchor FROM ai_memory_item WHERE tenant_id=OLD.tenant_id AND subject_type=OLD.subject_type AND subject_id=OLD.subject_id AND domain=OLD.domain AND scope_type=OLD.scope_type AND scope_id=OLD.scope_id AND purpose=OLD.purpose AND field_key=OLD.field_key FOR UPDATE;
 ELSEIF OLD.suppression_kind='SOURCE' THEN
  SELECT id INTO anchor FROM ai_memory_source WHERE tenant_id=OLD.tenant_id AND id=OLD.source_id FOR UPDATE;
 END IF;
END$$
CREATE TRIGGER trg_memory_suppression_delete BEFORE DELETE ON ai_memory_suppression FOR EACH ROW
BEGIN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_SUPPRESSION_DELETE_FORBIDDEN';
END$$
DELIMITER ;
