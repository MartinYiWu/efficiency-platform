-- S7 只读预检；不得在此文件执行任何写入或扩展安装。
SELECT current_setting('server_version') AS server_version;
SELECT current_user AS current_user_name, current_database() AS database_name;
SELECT current_setting('transaction_read_only') AS transaction_read_only;
SELECT EXISTS (
    SELECT 1 FROM pg_available_extensions WHERE name = 'vector'
) AS vector_available;
SELECT EXISTS (
    SELECT 1 FROM pg_extension WHERE extname = 'vector'
) AS vector_installed;
SELECT EXISTS (
    SELECT 1 FROM pg_namespace WHERE nspname = 's7_acceptance_00000000'
) AS target_schema_exists;
