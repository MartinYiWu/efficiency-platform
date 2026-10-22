-- 先回退应用并确认允许丢失新增元数据，取得独立授权后执行。
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE customer_service.document_parent
    DROP CONSTRAINT ck_customer_service_parent_evidence_mode,
    DROP CONSTRAINT ck_customer_service_parent_block_kind,
    DROP COLUMN evidence_mode,
    DROP COLUMN block_kind;
COMMIT;
