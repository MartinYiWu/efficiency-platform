-- V1.1.5 只读结构验证；不得在本文件写入业务数据。

SELECT table_name, column_name, column_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND (
      (table_name = 'ai_customer_service_conversation' AND column_name = 'last_message_at')
      OR (table_name = 'ai_customer_service_message' AND column_name IN ('content_markdown', 'status'))
  )
ORDER BY table_name, ordinal_position;

SELECT table_name, index_name, GROUP_CONCAT(column_name ORDER BY seq_in_index) AS indexed_columns
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'ai_customer_service_conversation'
  AND index_name = 'idx_ai_cs_conversation_last_message'
GROUP BY table_name, index_name;
