SELECT current_database() AS target_database;
SELECT column_name, is_nullable, data_type
FROM information_schema.columns
WHERE table_schema = 'customer_service'
  AND table_name = 'document_chunk'
  AND column_name IN ('document_title', 'version_no')
ORDER BY column_name;
