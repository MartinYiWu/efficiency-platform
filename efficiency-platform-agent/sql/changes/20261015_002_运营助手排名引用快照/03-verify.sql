SELECT table_name, engine, table_collation
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'agent_ranked_reference_snapshot';

SELECT index_name, non_unique,
       GROUP_CONCAT(column_name ORDER BY seq_in_index) AS columns_in_order
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'agent_ranked_reference_snapshot'
GROUP BY index_name, non_unique
ORDER BY index_name;

SELECT COUNT(*) AS ranked_reference_snapshot_count
FROM agent_ranked_reference_snapshot;
