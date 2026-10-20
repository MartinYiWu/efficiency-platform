-- 对应迁移：V1.1.0__customer_service_knowledge_aihub.sql。
-- 不可逆风险：下列操作永久删除智能客服、知识库和 AI 配置数据。
-- 执行前条件：仅在明确放弃本迁移且完成备份后人工执行。
-- 删除顺序按逻辑引用逆序排列，不影响迁移前既有对象。

DROP TABLE IF EXISTS sys_audit_log;
DROP TABLE IF EXISTS ai_customer_service_feedback;
DROP TABLE IF EXISTS ai_customer_service_citation;
DROP TABLE IF EXISTS ai_customer_service_run_step;
DROP TABLE IF EXISTS ai_customer_service_run;
DROP TABLE IF EXISTS ai_customer_service_message;
DROP TABLE IF EXISTS ai_customer_service_conversation;
DROP TABLE IF EXISTS ai_agent_release_snapshot;
DROP TABLE IF EXISTS ai_agent_release;
DROP TABLE IF EXISTS ai_agent_version_knowledge_binding;
DROP TABLE IF EXISTS ai_rag_policy;
DROP TABLE IF EXISTS ai_model_policy;
DROP TABLE IF EXISTS ai_agent_version_prompt_binding;
DROP TABLE IF EXISTS ai_prompt_variable;
DROP TABLE IF EXISTS ai_prompt_message_template;
DROP TABLE IF EXISTS ai_prompt_version;
DROP TABLE IF EXISTS ai_prompt_definition;
DROP TABLE IF EXISTS ai_agent_version;
DROP TABLE IF EXISTS ai_agent_definition;
DROP TABLE IF EXISTS kb_index_release_document;
DROP TABLE IF EXISTS kb_index_release;
DROP TABLE IF EXISTS kb_processing_task;
DROP TABLE IF EXISTS kb_ingest_item;
DROP TABLE IF EXISTS kb_ingest_batch;
DROP TABLE IF EXISTS kb_document_version;
DROP TABLE IF EXISTS kb_document;
DROP TABLE IF EXISTS kb_directory;
DROP TABLE IF EXISTS kb_knowledge_base;
DROP TABLE IF EXISTS pf_file_object;
