SELECT table_name, engine, table_collation
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('agent_run', 'agent_run_event', 'agent_request_deduplication')
ORDER BY table_name;

SELECT table_name, index_name, non_unique, GROUP_CONCAT(column_name ORDER BY seq_in_index) AS columns_in_order
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name IN ('agent_run', 'agent_run_event', 'agent_request_deduplication')
GROUP BY table_name, index_name, non_unique
ORDER BY table_name, index_name;

SELECT
    (SELECT COUNT(*) FROM agent_run) AS run_count,
    (SELECT COUNT(*) FROM agent_run_event) AS event_count,
    (SELECT COUNT(*) FROM agent_request_deduplication) AS request_count;
