-- V1.1.0 只读结构验证；不得在本文件写入业务数据。

SELECT expected.table_name, actual.table_name IS NOT NULL AS present
FROM (
    SELECT 'pf_file_object' AS table_name
    UNION ALL SELECT 'kb_knowledge_base'
    UNION ALL SELECT 'kb_directory'
    UNION ALL SELECT 'kb_document'
    UNION ALL SELECT 'kb_document_version'
    UNION ALL SELECT 'kb_ingest_batch'
    UNION ALL SELECT 'kb_ingest_item'
    UNION ALL SELECT 'kb_processing_task'
    UNION ALL SELECT 'kb_index_release'
    UNION ALL SELECT 'kb_index_release_document'
    UNION ALL SELECT 'ai_agent_definition'
    UNION ALL SELECT 'ai_agent_version'
    UNION ALL SELECT 'ai_prompt_definition'
    UNION ALL SELECT 'ai_prompt_version'
    UNION ALL SELECT 'ai_prompt_message_template'
    UNION ALL SELECT 'ai_prompt_variable'
    UNION ALL SELECT 'ai_agent_version_prompt_binding'
    UNION ALL SELECT 'ai_model_policy'
    UNION ALL SELECT 'ai_rag_policy'
    UNION ALL SELECT 'ai_agent_version_knowledge_binding'
    UNION ALL SELECT 'ai_agent_release'
    UNION ALL SELECT 'ai_agent_release_snapshot'
    UNION ALL SELECT 'ai_customer_service_conversation'
    UNION ALL SELECT 'ai_customer_service_message'
    UNION ALL SELECT 'ai_customer_service_run'
    UNION ALL SELECT 'ai_customer_service_run_step'
    UNION ALL SELECT 'ai_customer_service_citation'
    UNION ALL SELECT 'ai_customer_service_feedback'
    UNION ALL SELECT 'sys_audit_log'
) expected
LEFT JOIN information_schema.tables actual
  ON actual.table_schema = DATABASE()
 AND actual.table_name = expected.table_name
ORDER BY expected.table_name;

SELECT table_name, index_name, non_unique, GROUP_CONCAT(column_name ORDER BY seq_in_index) AS indexed_columns
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name IN (
      'pf_file_object', 'kb_knowledge_base', 'kb_document_version',
      'kb_index_release', 'ai_agent_definition', 'ai_prompt_definition',
      'ai_model_policy', 'ai_rag_policy', 'ai_agent_release_snapshot',
      'ai_customer_service_message', 'ai_customer_service_run',
      'ai_customer_service_citation', 'ai_customer_service_feedback'
  )
GROUP BY table_name, index_name, non_unique
ORDER BY table_name, index_name;

SELECT table_name, column_name, data_type, column_type, is_nullable
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND (
      (table_name = 'kb_document_version' AND column_name IN ('status', 'parse_metadata', 'file_sha256'))
      OR (table_name = 'ai_prompt_message_template' AND column_name IN ('role', 'content_template', 'trusted_instruction'))
      OR (table_name = 'ai_agent_release_snapshot' AND column_name IN ('snapshot_json', 'checksum', 'agent_ack_status'))
      OR (table_name = 'ai_customer_service_citation' AND column_name IN ('chunk_id', 'quoted_text', 'content_hash'))
  )
ORDER BY table_name, ordinal_position;
