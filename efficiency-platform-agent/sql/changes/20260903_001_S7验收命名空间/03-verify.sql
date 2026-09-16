-- S7 只读结构和隔离验证；不得写入数据。
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 's7_acceptance_00000000'
ORDER BY table_name;
SELECT column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_schema = 's7_acceptance_00000000' AND table_name = 'chunks'
ORDER BY ordinal_position;
SELECT to_tsvector('simple', 's7 verification') @@ plainto_tsquery('simple', 'verification') AS fts_available;
SELECT extname FROM pg_extension WHERE extname = 'vector';
