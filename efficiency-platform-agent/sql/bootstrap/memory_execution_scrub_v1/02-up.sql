ALTER TABLE agent_memory_invalidation_receipt
 ADD COLUMN cleanup_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
 ADD COLUMN stop_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
 ADD COLUMN expected_execution_revision BIGINT UNSIGNED NULL,
 ADD COLUMN grant_epoch BIGINT UNSIGNED NULL,
 ADD COLUMN source_epoch BIGINT UNSIGNED NULL,
 ADD COLUMN deletion_epoch BIGINT UNSIGNED NULL,
 ADD COLUMN threads_receipt VARCHAR(160) CHARACTER SET ascii COLLATE ascii_bin NULL,
 ADD COLUMN scrub_receipt VARCHAR(160) CHARACTER SET ascii COLLATE ascii_bin NULL;

ALTER TABLE agent_memory_execution
 DROP CHECK ck_memory_execution_state,
 MODIFY snapshot_ciphertext LONGBLOB NULL,
 MODIFY snapshot_nonce BINARY(12) NULL,
 ADD COLUMN scrub_event_id VARBINARY(512) NULL,
 ADD COLUMN scrub_authority JSON NULL,
 ADD CONSTRAINT ck_memory_execution_state CHECK(state IN ('ACTIVE','REVOKED','SCRUBBED')),
 ADD CONSTRAINT ck_memory_execution_body CHECK((state='SCRUBBED' AND snapshot_ciphertext IS NULL AND snapshot_nonce IS NULL AND scrub_event_id IS NOT NULL AND scrub_authority IS NOT NULL AND JSON_TYPE(scrub_authority)='OBJECT') OR (state IN ('ACTIVE','REVOKED') AND snapshot_ciphertext IS NOT NULL AND snapshot_nonce IS NOT NULL AND scrub_event_id IS NULL AND scrub_authority IS NULL));

DELIMITER $$
CREATE TRIGGER trg_memory_execution_scrub BEFORE UPDATE ON agent_memory_execution FOR EACH ROW
BEGIN
 DECLARE proofs INT DEFAULT 0;
 IF OLD.tenant_id<>NEW.tenant_id OR OLD.execution_id<>NEW.execution_id OR OLD.runtime_id<>NEW.runtime_id OR OLD.runtime_kind<>NEW.runtime_kind OR OLD.request_fingerprint<>NEW.request_fingerprint OR OLD.context_fingerprint<>NEW.context_fingerprint OR OLD.original_deadline<>NEW.original_deadline OR OLD.execution_revision<>NEW.execution_revision OR OLD.key_version<>NEW.key_version THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_EXECUTION_ANCHOR_IMMUTABLE';
 END IF;
 IF NEW.grant_epoch<OLD.grant_epoch OR NEW.source_epoch<OLD.source_epoch OR NEW.deletion_epoch<OLD.deletion_epoch OR (OLD.state='SCRUBBED' AND NEW.state<>'SCRUBBED') OR (OLD.state='REVOKED' AND NEW.state='ACTIVE') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_EXECUTION_RESURRECTION_FORBIDDEN';
 END IF;
 IF OLD.state='SCRUBBED' AND (NOT(NEW.scrub_event_id<=>OLD.scrub_event_id) OR NOT(NEW.scrub_authority<=>OLD.scrub_authority)) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_SCRUB_AUTHORITY_IMMUTABLE'; END IF;
 IF NEW.state='SCRUBBED' AND OLD.state<>'SCRUBBED' THEN
  SELECT COUNT(*) INTO proofs FROM agent_memory_invalidation_receipt WHERE tenant_id=OLD.tenant_id AND execution_id=OLD.execution_id AND event_id=NEW.scrub_event_id AND expected_execution_revision=NEW.execution_revision AND grant_epoch=NEW.grant_epoch AND source_epoch=NEW.source_epoch AND deletion_epoch=NEW.deletion_epoch AND stop_confirmed=TRUE AND threads_receipt IS NOT NULL AND scrub_receipt IS NOT NULL AND cleanup_fingerprint IS NOT NULL FOR UPDATE;
  IF OLD.state<>'REVOKED' OR proofs=0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_EXECUTION_SCRUB_PROOF_REQUIRED'; END IF;
 END IF;
END$$
DELIMITER ;
