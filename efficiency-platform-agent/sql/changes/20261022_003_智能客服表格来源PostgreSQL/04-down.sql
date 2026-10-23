BEGIN;
ALTER TABLE customer_service.document_parent DROP COLUMN source_table_id;
COMMIT;
