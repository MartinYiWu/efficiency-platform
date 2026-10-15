SELECT DATABASE() AS target_database, VERSION() AS mysql_version;

SELECT table_name
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('agent_run', 'agent_run_event', 'agent_request_deduplication')
ORDER BY table_name;
