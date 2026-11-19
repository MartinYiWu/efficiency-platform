-- D30KB：知识拥有模块refs-only source生命周期outbox；默认不开，不触付费账本。
SET SESSION lock_wait_timeout=5;
CREATE TABLE kb_memory_source_outbox (
 event_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 tenant_id VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
 knowledge_base_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 reason VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 status VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'PENDING',
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(event_id),KEY ix_kb_memory_event_delivery(status,created_at,event_id),
 CONSTRAINT ck_kb_memory_event CHECK(reason IN ('INDEX_RELEASE_CHANGED','BASE_POLICY_CHANGED','DOCUMENT_STATE_CHANGED') AND status IN ('PENDING','DELIVERED'))
) ENGINE=InnoDB;
