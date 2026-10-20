-- 只读预检；目标数据库必须是开发库 vector。
SELECT current_database() AS target_database,
       current_user AS current_user_name,
       current_setting('server_version') AS server_version,
       current_setting('transaction_read_only') AS transaction_read_only;

SELECT EXISTS (
    SELECT 1 FROM pg_extension WHERE extname = 'vector'
) AS vector_installed;

SELECT nspname AS conflicting_schema
FROM pg_namespace
WHERE nspname = 'customer_service';

SELECT table_schema, table_name AS conflicting_table
FROM information_schema.tables
WHERE table_schema = 'customer_service'
  AND table_name IN ('document_chunk', 'index_release_document')
ORDER BY table_name;
