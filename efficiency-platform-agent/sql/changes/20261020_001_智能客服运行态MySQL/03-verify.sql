-- 只读验证，不写入运行数据。
SELECT expected.table_name, actual.table_name IS NOT NULL AS present
FROM (
    SELECT 'agent_release_bundle' AS table_name
    UNION ALL SELECT 'agent_customer_service_retrieval_snapshot'
) expected
LEFT JOIN information_schema.tables actual
  ON actual.table_schema = DATABASE()
 AND actual.table_name = expected.table_name
ORDER BY expected.table_name;

SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name IN (
      'agent_release_bundle',
      'agent_customer_service_retrieval_snapshot'
  )
ORDER BY table_name, ordinal_position;

SELECT table_name, index_name, non_unique,
       GROUP_CONCAT(column_name ORDER BY seq_in_index) AS indexed_columns
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name IN (
      'agent_release_bundle',
      'agent_customer_service_retrieval_snapshot'
  )
GROUP BY table_name, index_name, non_unique
ORDER BY table_name, index_name;

SELECT table_name AS required_runtime_table, COUNT(*) AS present_count
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('agent_run', 'agent_run_event', 'agent_run_prompt_snapshot')
GROUP BY table_name
ORDER BY table_name;
