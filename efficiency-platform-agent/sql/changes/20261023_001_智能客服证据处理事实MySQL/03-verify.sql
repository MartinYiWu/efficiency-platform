-- 只读验证列类型、可空性与原有唯一约束。
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'agent_customer_service_retrieval_snapshot'
  AND column_name = 'retrieval_facts_json';
SELECT index_name, non_unique,
       GROUP_CONCAT(column_name ORDER BY seq_in_index) AS indexed_columns
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'agent_customer_service_retrieval_snapshot'
GROUP BY index_name, non_unique;
SELECT COUNT(*) AS rows_without_new_facts
FROM agent_customer_service_retrieval_snapshot
WHERE retrieval_facts_json IS NULL;
