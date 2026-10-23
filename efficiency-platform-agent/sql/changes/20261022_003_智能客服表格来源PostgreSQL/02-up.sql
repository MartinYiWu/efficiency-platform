BEGIN;
ALTER TABLE customer_service.document_parent
    ADD COLUMN source_table_id bigint NULL
    CONSTRAINT document_parent_source_table_id_nonnegative CHECK (source_table_id >= 0);
COMMENT ON COLUMN customer_service.document_parent.source_table_id
    IS '规范化解析文档内原始表块起始偏移；仅新版本冻结，旧记录为空禁止表格分组';
COMMIT;
