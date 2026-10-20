-- 只读预检；目标必须是 Agent MySQL 开发库。
SELECT DATABASE() AS target_database, VERSION() AS mysql_version;

SELECT table_name AS required_runtime_table, COUNT(*) AS present_count
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('agent_run', 'agent_run_event', 'agent_run_prompt_snapshot')
GROUP BY table_name
ORDER BY table_name;

SELECT table_name AS conflicting_table
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
      'agent_release_bundle',
      'agent_customer_service_retrieval_snapshot'
  )
ORDER BY table_name;
