-- 目标环境：开发环境 Java MySQL。
-- 影响范围：只读检查 AI 智能客服首个闭环涉及的新增表与迁移版本。
-- 前置检查：确认 DATABASE() 为本项目 Java 开发库，且不是生产库。
-- 授权要求：执行 V1.1.0 前人工运行；发现任何冲突必须停止迁移。
-- 失败处理：不得覆盖同名表，不得复用已执行的迁移版本。
-- 回滚方式：只读脚本无需回滚。

SELECT DATABASE() AS target_database, VERSION() AS mysql_version;

SELECT table_name AS conflicting_table
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
      'pf_file_object',
      'kb_knowledge_base', 'kb_directory', 'kb_document', 'kb_document_version',
      'kb_ingest_batch', 'kb_ingest_item', 'kb_processing_task',
      'kb_index_release', 'kb_index_release_document',
      'ai_agent_definition', 'ai_agent_version',
      'ai_prompt_definition', 'ai_prompt_version', 'ai_prompt_message_template',
      'ai_prompt_variable', 'ai_agent_version_prompt_binding',
      'ai_model_policy', 'ai_rag_policy', 'ai_agent_version_knowledge_binding',
      'ai_agent_release', 'ai_agent_release_snapshot',
      'ai_customer_service_conversation', 'ai_customer_service_message',
      'ai_customer_service_run', 'ai_customer_service_run_step',
      'ai_customer_service_citation', 'ai_customer_service_feedback',
      'sys_audit_log'
  )
ORDER BY table_name;

SET @flyway_check_sql = IF(
    EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = 'flyway_schema_history'
    ),
    'SELECT version, description, success FROM flyway_schema_history WHERE version = ''1.1.0''',
    'SELECT ''flyway_schema_history_not_present'' AS migration_history_status'
);
PREPARE flyway_check_statement FROM @flyway_check_sql;
EXECUTE flyway_check_statement;
DEALLOCATE PREPARE flyway_check_statement;
