-- 仅在确认不存在依赖父子片段的已发布索引后，经单独授权回滚。
DROP INDEX IF EXISTS customer_service.idx_customer_service_child_parent;
ALTER TABLE customer_service.document_chunk
    DROP CONSTRAINT IF EXISTS ck_customer_service_child_position,
    DROP CONSTRAINT IF EXISTS fk_customer_service_child_parent_version,
    DROP COLUMN IF EXISTS end_offset,
    DROP COLUMN IF EXISTS start_offset,
    DROP COLUMN IF EXISTS child_no,
    DROP COLUMN IF EXISTS parent_id;
DROP TABLE IF EXISTS customer_service.document_parent;
