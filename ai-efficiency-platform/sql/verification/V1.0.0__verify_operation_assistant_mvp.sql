SELECT table_name, engine, table_collation
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
      'ai_operation_conversation',
      'ai_operation_message',
      'ai_operation_run',
      'ai_operation_artifact'
  )
ORDER BY table_name;

SELECT table_name, index_name, non_unique, GROUP_CONCAT(column_name ORDER BY seq_in_index) AS columns_in_order
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name IN (
      'ai_operation_conversation',
      'ai_operation_message',
      'ai_operation_run',
      'ai_operation_artifact'
  )
GROUP BY table_name, index_name, non_unique
ORDER BY table_name, index_name;

SELECT
    (SELECT COUNT(*) FROM ai_operation_conversation) AS conversation_count,
    (SELECT COUNT(*) FROM ai_operation_message) AS message_count,
    (SELECT COUNT(*) FROM ai_operation_run) AS run_count,
    (SELECT COUNT(*) FROM ai_operation_artifact) AS artifact_count;
