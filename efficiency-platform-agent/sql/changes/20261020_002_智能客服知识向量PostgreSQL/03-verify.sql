-- 只读结构验证，不写入 Chunk 或索引成员。
SELECT current_database() AS target_database;
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

SELECT expected.table_name, actual.table_name IS NOT NULL AS present
FROM (
    VALUES ('document_chunk'), ('index_release_document')
) AS expected(table_name)
LEFT JOIN information_schema.tables actual
  ON actual.table_schema = 'customer_service'
 AND actual.table_name = expected.table_name
ORDER BY expected.table_name;

SELECT a.attname AS column_name,
       format_type(a.atttypid, a.atttypmod) AS formatted_type,
       a.attnotnull AS not_null
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'customer_service'
  AND c.relname = 'document_chunk'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;

SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'customer_service'
ORDER BY tablename, indexname;

SELECT conname, pg_get_constraintdef(oid) AS constraint_definition
FROM pg_constraint
WHERE connamespace = 'customer_service'::regnamespace
ORDER BY conrelid::regclass::text, conname;
