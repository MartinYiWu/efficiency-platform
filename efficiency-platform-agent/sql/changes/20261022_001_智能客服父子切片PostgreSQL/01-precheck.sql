-- 只读预检，不执行 DDL。
SELECT current_database() AS target_database,
       current_setting('transaction_read_only') AS transaction_read_only;

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'customer_service'
  AND table_name IN ('document_chunk', 'document_parent')
ORDER BY table_name;

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'customer_service'
  AND table_name = 'document_chunk'
  AND column_name IN ('parent_id', 'child_no', 'start_offset', 'end_offset')
ORDER BY column_name;
