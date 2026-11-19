-- D28：本域ACL/显式共享投影；默认关闭；仅授权环境执行，不初始化外部账本或业务project。
SET SESSION lock_wait_timeout=5;
SET SESSION innodb_lock_wait_timeout=5;
CREATE TABLE ai_memory_sharing_scope (
 tenant_id VARBINARY(512) NOT NULL,id VARBINARY(512) NOT NULL,scope_type VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 department_id VARBINARY(512) NULL,owner_id VARBINARY(512) NOT NULL,approver_id VARBINARY(512) NOT NULL,
 status VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,revision BIGINT UNSIGNED NOT NULL,expires_at DATETIME(6) NOT NULL,
 request_id VARBINARY(512) NOT NULL,fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 PRIMARY KEY(tenant_id,id),UNIQUE KEY uk_sharing_scope_request(tenant_id,request_id),
 CONSTRAINT ck_sharing_scope CHECK(scope_type IN ('PROJECT','DEPARTMENT','ORGANIZATION') AND status IN ('PENDING','ACTIVE') AND owner_id<>approver_id AND ((scope_type='DEPARTMENT' AND department_id IS NOT NULL) OR (scope_type<>'DEPARTMENT' AND department_id IS NULL)))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
CREATE TABLE ai_memory_sharing_member (
 tenant_id VARBINARY(512) NOT NULL,scope_id VARBINARY(512) NOT NULL,user_id VARBINARY(512) NOT NULL,
 status VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,revision BIGINT UNSIGNED NOT NULL,request_id VARBINARY(512) NOT NULL,
 PRIMARY KEY(tenant_id,scope_id,user_id),CONSTRAINT fk_sharing_member_scope FOREIGN KEY(tenant_id,scope_id) REFERENCES ai_memory_sharing_scope(tenant_id,id),
 CONSTRAINT ck_sharing_member CHECK(status IN ('INVITED','ACTIVE','LEFT') AND OCTET_LENGTH(user_id)>0)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
CREATE TABLE ai_memory_sharing_grant (
 tenant_id VARBINARY(512) NOT NULL,id VARBINARY(512) NOT NULL,scope_id VARBINARY(512) NULL,owner_id VARBINARY(512) NOT NULL,
 item_id VARBINARY(512) NOT NULL,version_id VARBINARY(512) NOT NULL,field_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 origin_agent VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,allowed_agents_json JSON NOT NULL,
 status VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,revision BIGINT UNSIGNED NOT NULL,item_revision BIGINT UNSIGNED NOT NULL,
 expires_at DATETIME(6) NOT NULL,request_id VARBINARY(512) NOT NULL,fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 PRIMARY KEY(tenant_id,id),UNIQUE KEY uk_sharing_grant_request(tenant_id,request_id),KEY ix_sharing_grant_owner(tenant_id,owner_id),
 CONSTRAINT fk_sharing_grant_scope FOREIGN KEY(tenant_id,scope_id) REFERENCES ai_memory_sharing_scope(tenant_id,id),
 CONSTRAINT fk_sharing_grant_version FOREIGN KEY(tenant_id,item_id,version_id) REFERENCES ai_memory_version(tenant_id,item_id,id),
 CONSTRAINT ck_sharing_grant CHECK(field_key IN ('response.language','response.detail_level','response.format') AND origin_agent IN ('operations','customer-service') AND status IN ('PENDING','ACTIVE','REVOKED') AND JSON_TYPE(allowed_agents_json)='ARRAY' AND JSON_LENGTH(allowed_agents_json) BETWEEN 1 AND 2)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
CREATE TABLE ai_memory_sharing_projection (
 tenant_id VARBINARY(512) NOT NULL,id VARBINARY(512) NOT NULL,grant_id VARBINARY(512) NOT NULL,user_id VARBINARY(512) NOT NULL,
 target_agent VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,grant_revision BIGINT UNSIGNED NOT NULL,member_revision BIGINT UNSIGNED NOT NULL,
 state VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,expires_at DATETIME(6) NOT NULL,cleanup_deadline DATETIME(6) NULL,
 PRIMARY KEY(tenant_id,id),UNIQUE KEY uk_sharing_projection(tenant_id,grant_id,user_id,target_agent,grant_revision,member_revision),
 KEY ix_sharing_projection_reader(tenant_id,user_id,target_agent),
 CONSTRAINT fk_sharing_projection_grant FOREIGN KEY(tenant_id,grant_id) REFERENCES ai_memory_sharing_grant(tenant_id,id),
 CONSTRAINT ck_sharing_projection CHECK(target_agent IN ('operations','customer-service') AND state IN ('ACTIVE','REVOKED') AND ((state='ACTIVE' AND cleanup_deadline IS NULL) OR (state='REVOKED' AND cleanup_deadline IS NOT NULL)))
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC;
DELIMITER $$
CREATE TRIGGER trg_sharing_grant_update BEFORE UPDATE ON ai_memory_sharing_grant FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.scope_id<=>OLD.scope_id) OR NOT(NEW.owner_id<=>OLD.owner_id) OR NOT(NEW.item_id<=>OLD.item_id) OR NOT(NEW.version_id<=>OLD.version_id) OR NOT(NEW.field_key<=>OLD.field_key) OR NOT(NEW.origin_agent<=>OLD.origin_agent) OR NOT(NEW.allowed_agents_json<=>OLD.allowed_agents_json) OR NOT(NEW.item_revision<=>OLD.item_revision) OR NOT(NEW.expires_at<=>OLD.expires_at) OR NOT(NEW.request_id<=>OLD.request_id) OR NOT(NEW.fingerprint<=>OLD.fingerprint) OR NEW.revision<>OLD.revision+1 OR NOT((OLD.status='PENDING' AND NEW.status IN ('ACTIVE','REVOKED')) OR (OLD.status='ACTIVE' AND NEW.status='REVOKED')) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SHARING_GRANT_IMMUTABLE'; END IF;
END$$
CREATE TRIGGER trg_sharing_scope_update BEFORE UPDATE ON ai_memory_sharing_scope FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.scope_type<=>OLD.scope_type) OR NOT(NEW.department_id<=>OLD.department_id) OR NOT(NEW.owner_id<=>OLD.owner_id) OR NOT(NEW.approver_id<=>OLD.approver_id) OR NOT(NEW.expires_at<=>OLD.expires_at) OR NOT(NEW.request_id<=>OLD.request_id) OR NOT(NEW.fingerprint<=>OLD.fingerprint) OR NEW.revision<>OLD.revision+1 OR NOT((OLD.status='PENDING' AND NEW.status='ACTIVE') OR (OLD.status='ACTIVE' AND NEW.status='ACTIVE')) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SHARING_SCOPE_IMMUTABLE'; END IF;
END$$
CREATE TRIGGER trg_sharing_member_update BEFORE UPDATE ON ai_memory_sharing_member FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.scope_id<=>OLD.scope_id) OR NOT(NEW.user_id<=>OLD.user_id) OR NEW.revision<>OLD.revision+1 OR NOT((OLD.status='INVITED' AND NEW.status IN ('ACTIVE','LEFT')) OR (OLD.status='ACTIVE' AND NEW.status='LEFT')) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SHARING_MEMBERSHIP_IMMUTABLE'; END IF;
END$$
CREATE TRIGGER trg_sharing_projection_update BEFORE UPDATE ON ai_memory_sharing_projection FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.grant_id<=>OLD.grant_id) OR NOT(NEW.user_id<=>OLD.user_id) OR NOT(NEW.target_agent<=>OLD.target_agent) OR NOT(NEW.grant_revision<=>OLD.grant_revision) OR NOT(NEW.member_revision<=>OLD.member_revision) OR NOT(NEW.expires_at<=>OLD.expires_at) OR NOT(OLD.state='ACTIVE' AND NEW.state='REVOKED') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SHARING_PROJECTION_IMMUTABLE'; END IF;
END$$
CREATE TRIGGER trg_sharing_scope_delete BEFORE DELETE ON ai_memory_sharing_scope FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SHARING_DELETE_FORBIDDEN'; END$$
CREATE TRIGGER trg_sharing_member_delete BEFORE DELETE ON ai_memory_sharing_member FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SHARING_DELETE_FORBIDDEN'; END$$
CREATE TRIGGER trg_sharing_grant_delete BEFORE DELETE ON ai_memory_sharing_grant FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SHARING_DELETE_FORBIDDEN'; END$$
CREATE TRIGGER trg_sharing_projection_delete BEFORE DELETE ON ai_memory_sharing_projection FOR EACH ROW BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SHARING_DELETE_FORBIDDEN'; END$$
DELIMITER ;
