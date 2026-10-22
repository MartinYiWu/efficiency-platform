-- 仅新增可空列；不回填或改写已发布版本。
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE customer_service.document_parent
    ADD COLUMN block_kind TEXT,
    ADD COLUMN evidence_mode TEXT,
    ADD CONSTRAINT ck_customer_service_parent_block_kind
        CHECK (block_kind IS NULL OR block_kind IN ('NUMBERED_RULE', 'LIST', 'TABLE', 'CODE', 'PARAGRAPH')),
    ADD CONSTRAINT ck_customer_service_parent_evidence_mode
        CHECK (evidence_mode IS NULL OR evidence_mode IN ('FULL_ONLY', 'EXTRACTIVE_NARRATIVE'));
COMMIT;
