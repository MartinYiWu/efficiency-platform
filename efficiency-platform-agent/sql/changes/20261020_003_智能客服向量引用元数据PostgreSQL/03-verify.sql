SELECT column_name, is_nullable, data_type
FROM information_schema.columns
WHERE table_schema = 'customer_service'
  AND table_name = 'document_chunk'
  AND column_name IN ('document_title', 'version_no')
ORDER BY column_name;

SELECT COUNT(*) AS invalid_rows
FROM customer_service.document_chunk
WHERE document_title IS NULL OR length(btrim(document_title)) = 0
   OR version_no IS NULL OR version_no <= 0;
