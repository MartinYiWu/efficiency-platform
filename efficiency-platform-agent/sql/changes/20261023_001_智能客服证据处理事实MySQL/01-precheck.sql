-- 只读预检；目标必须为 ai_efficiency_platform_agent。
SELECT DATABASE() AS target_database, VERSION() AS mysql_version;
SELECT table_name
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'agent_customer_service_retrieval_snapshot';
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'agent_customer_service_retrieval_snapshot'
ORDER BY ordinal_position;
