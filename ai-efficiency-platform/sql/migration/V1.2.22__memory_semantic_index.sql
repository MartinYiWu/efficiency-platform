-- D26 Java refs-only index jobs; no schema is installed at application startup.
SET SESSION lock_wait_timeout=5;
SET SESSION innodb_lock_wait_timeout=5;
CREATE TABLE ai_memory_index_job (
 tenant_id VARBINARY(512) NOT NULL,id VARBINARY(512) NOT NULL,user_id VARBINARY(512) NOT NULL,
 domain VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 item_id VARBINARY(512) NOT NULL,version_id VARBINARY(512) NOT NULL,
 generation BIGINT UNSIGNED NOT NULL,deletion_epoch BIGINT UNSIGNED NOT NULL,
 source_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 embedding_model VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,dimension INT NOT NULL,
 policy_version VARCHAR(128) NOT NULL,execution_id VARBINARY(512) NOT NULL,task_id VARBINARY(512) NOT NULL,
 execution_scope_json JSON NOT NULL,expires_at DATETIME(6) NOT NULL,
 state VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 request_id VARBINARY(512) NOT NULL,request_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 delete_epoch BIGINT UNSIGNED NOT NULL DEFAULT 0,delete_receipt_ref VARCHAR(160) CHARACTER SET ascii COLLATE ascii_bin NULL,
 PRIMARY KEY(tenant_id,id),UNIQUE KEY uk_memory_index_request(tenant_id,request_id),
 UNIQUE KEY uk_memory_index_version(tenant_id,item_id,version_id,generation,embedding_model,dimension,policy_version),
 KEY ix_memory_index_ready(tenant_id,user_id,domain,state),
 CONSTRAINT fk_memory_index_version FOREIGN KEY(tenant_id,item_id,version_id) REFERENCES ai_memory_version(tenant_id,item_id,id),
 CONSTRAINT fk_memory_index_execution FOREIGN KEY(tenant_id,execution_id) REFERENCES ai_memory_packet(tenant_id,execution_id),
 CONSTRAINT ck_memory_index_job CHECK(domain IN ('operations','customer-service') AND generation>0 AND dimension BETWEEN 1 AND 4096 AND state IN ('QUEUED','SENDING','READY','UNKNOWN','DELETE_PENDING','DELETED') AND REGEXP_LIKE(source_fingerprint,'^[0-9a-f]{64}$','c') AND REGEXP_LIKE(request_fingerprint,'^[0-9a-f]{64}$','c'))
,
 CONSTRAINT ck_memory_index_delete CHECK(delete_epoch>=deletion_epoch AND ((state='DELETED' AND delete_receipt_ref IS NOT NULL AND OCTET_LENGTH(delete_receipt_ref)>0) OR (state<>'DELETED' AND delete_receipt_ref IS NULL)))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
DELIMITER $$
CREATE TRIGGER trg_memory_index_job_insert BEFORE INSERT ON ai_memory_index_job FOR EACH ROW
BEGIN
 DECLARE matches INT DEFAULT 0;
 SELECT COUNT(*) INTO matches FROM ai_memory_item i JOIN ai_memory_version v ON v.tenant_id=i.tenant_id AND v.item_id=i.id AND v.id=i.current_version_id
 WHERE i.tenant_id=NEW.tenant_id AND i.id=NEW.item_id AND v.id=NEW.version_id AND i.owner_id=NEW.user_id AND i.subject_id=NEW.user_id
  AND i.domain=CAST(NEW.domain AS BINARY) AND i.origin_top_agent_id=CAST(NEW.domain AS BINARY) AND i.lifecycle='LIVE' AND v.status='ACTIVE'
  AND i.revision=NEW.generation AND v.expires_at>UTC_TIMESTAMP(6)
  AND EXISTS(SELECT 1 FROM ai_memory_dependency d WHERE d.tenant_id=i.tenant_id AND d.target_type='MEMORY_VERSION' AND d.target_id=i.id AND d.target_version=v.id)
  AND NOT EXISTS(SELECT 1 FROM ai_memory_dependency d LEFT JOIN ai_memory_source s ON s.tenant_id=d.tenant_id AND s.id=d.source_id
   WHERE d.tenant_id=i.tenant_id AND d.target_type='MEMORY_VERSION' AND d.target_id=i.id AND d.target_version=v.id
    AND (s.id IS NULL OR s.grant_epoch<>d.grant_epoch OR s.source_epoch<>d.source_epoch OR s.deletion_epoch<>d.deletion_epoch OR s.retention_deadline IS NULL OR s.retention_deadline<=UTC_TIMESTAMP(6)
     OR EXISTS(SELECT 1 FROM ai_memory_tombstone t WHERE t.tenant_id=s.tenant_id AND t.target_type='SOURCE' AND t.target_id=s.id
      AND (s.grant_epoch<=t.grant_epoch OR s.source_epoch<t.source_epoch OR s.deletion_epoch<t.deletion_epoch))))
 LOCK IN SHARE MODE;
 IF matches<>1 OR NEW.state<>'QUEUED' OR NEW.delete_receipt_ref IS NOT NULL OR NEW.delete_epoch<>NEW.deletion_epoch THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_INDEX_CURRENT_SOURCE_REQUIRED'; END IF;
END$$
CREATE TRIGGER trg_memory_index_job_update BEFORE UPDATE ON ai_memory_index_job FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.user_id<=>OLD.user_id) OR NOT(NEW.domain<=>OLD.domain) OR NOT(NEW.item_id<=>OLD.item_id) OR NOT(NEW.version_id<=>OLD.version_id) OR NOT(NEW.generation<=>OLD.generation) OR NOT(NEW.deletion_epoch<=>OLD.deletion_epoch) OR NOT(NEW.source_fingerprint<=>OLD.source_fingerprint) OR NOT(NEW.embedding_model<=>OLD.embedding_model) OR NOT(NEW.dimension<=>OLD.dimension) OR NOT(NEW.policy_version<=>OLD.policy_version) OR NOT(NEW.execution_id<=>OLD.execution_id) OR NOT(NEW.task_id<=>OLD.task_id) OR NOT(NEW.execution_scope_json<=>OLD.execution_scope_json) OR NOT(NEW.expires_at<=>OLD.expires_at) OR NOT(NEW.request_id<=>OLD.request_id) OR NOT(NEW.request_fingerprint<=>OLD.request_fingerprint) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_INDEX_JOB_IMMUTABLE'; END IF;
 IF NEW.delete_epoch<OLD.delete_epoch OR (NEW.delete_epoch<>OLD.delete_epoch AND NEW.state<>'DELETE_PENDING')
  OR (NOT(NEW.delete_receipt_ref<=>OLD.delete_receipt_ref) AND NOT(OLD.state='DELETE_PENDING' AND NEW.state='DELETED')) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_INDEX_DELETE_ANCHOR_INVALID'; END IF;
 IF NOT((OLD.state='QUEUED' AND NEW.state='SENDING') OR (OLD.state='SENDING' AND NEW.state IN ('READY','UNKNOWN')) OR (OLD.state IN ('QUEUED','SENDING','READY','UNKNOWN') AND NEW.state='DELETE_PENDING') OR (OLD.state='DELETE_PENDING' AND NEW.state='DELETED')) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_INDEX_JOB_STATE_INVALID'; END IF;
END$$
CREATE TRIGGER trg_memory_index_job_delete BEFORE DELETE ON ai_memory_index_job FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_INDEX_JOB_DELETE_FORBIDDEN'; END$$
CREATE TRIGGER trg_memory_index_source_revoke AFTER UPDATE ON ai_memory_source FOR EACH ROW
BEGIN
 IF NEW.grant_epoch>OLD.grant_epoch OR NEW.source_epoch>OLD.source_epoch OR NEW.deletion_epoch>OLD.deletion_epoch
  OR (OLD.retention_deadline IS NOT NULL AND (NEW.retention_deadline IS NULL OR NEW.retention_deadline<OLD.retention_deadline)) THEN
  UPDATE ai_memory_index_job j SET j.state='DELETE_PENDING',j.delete_epoch=GREATEST(j.delete_epoch,NEW.deletion_epoch)
   WHERE j.tenant_id=NEW.tenant_id AND j.state IN ('QUEUED','SENDING','READY','UNKNOWN') AND EXISTS(
    SELECT 1 FROM ai_memory_dependency d WHERE d.tenant_id=j.tenant_id AND d.source_id=NEW.id AND d.target_type='MEMORY_VERSION' AND d.target_id=j.item_id AND d.target_version=j.version_id);
 END IF;
END$$
CREATE TRIGGER trg_memory_index_version_revoke AFTER UPDATE ON ai_memory_version FOR EACH ROW
BEGIN
 IF NEW.status<>'ACTIVE' OR NEW.grant_epoch>OLD.grant_epoch OR NEW.source_epoch>OLD.source_epoch OR NEW.deletion_epoch>OLD.deletion_epoch THEN
  UPDATE ai_memory_index_job j SET j.state='DELETE_PENDING',j.delete_epoch=GREATEST(j.delete_epoch,NEW.deletion_epoch)
   WHERE j.tenant_id=NEW.tenant_id AND j.item_id=NEW.item_id AND j.version_id=NEW.id AND j.state IN ('QUEUED','SENDING','READY','UNKNOWN');
 END IF;
END$$
DELIMITER ;
