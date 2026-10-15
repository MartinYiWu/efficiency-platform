SELECT DATABASE() AS target_database, VERSION() AS mysql_version;

SELECT table_name
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'agent_ranked_reference_snapshot';

SELECT COUNT(*) AS agent_run_table_count
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'agent_run';
