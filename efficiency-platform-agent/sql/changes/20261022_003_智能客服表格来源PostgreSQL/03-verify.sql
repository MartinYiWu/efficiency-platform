SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'customer_service' AND table_name = 'document_parent'
  AND column_name = 'source_table_id';
SELECT COUNT(*) AS invalid_source_count FROM customer_service.document_parent
WHERE source_table_id < 0 OR (source_table_id IS NOT NULL AND block_kind <> 'TABLE');
