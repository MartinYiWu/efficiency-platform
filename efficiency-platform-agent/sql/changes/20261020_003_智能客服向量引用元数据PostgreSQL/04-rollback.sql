ALTER TABLE customer_service.document_chunk
    DROP CONSTRAINT IF EXISTS ck_customer_service_chunk_title,
    DROP CONSTRAINT IF EXISTS ck_customer_service_chunk_version,
    DROP COLUMN IF EXISTS document_title,
    DROP COLUMN IF EXISTS version_no;
