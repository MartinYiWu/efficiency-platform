ALTER TABLE customer_service.document_chunk
    ADD COLUMN IF NOT EXISTS document_title TEXT,
    ADD COLUMN IF NOT EXISTS version_no INTEGER;

UPDATE customer_service.document_chunk
SET document_title = COALESCE(document_title, '历史文档 ' || document_id::text),
    version_no = COALESCE(version_no, 1)
WHERE document_title IS NULL OR version_no IS NULL;

ALTER TABLE customer_service.document_chunk
    ALTER COLUMN document_title SET NOT NULL,
    ALTER COLUMN version_no SET NOT NULL;

ALTER TABLE customer_service.document_chunk
    DROP CONSTRAINT IF EXISTS ck_customer_service_chunk_title,
    DROP CONSTRAINT IF EXISTS ck_customer_service_chunk_version;

ALTER TABLE customer_service.document_chunk
    ADD CONSTRAINT ck_customer_service_chunk_title
        CHECK (length(btrim(document_title)) > 0),
    ADD CONSTRAINT ck_customer_service_chunk_version
        CHECK (version_no > 0);
