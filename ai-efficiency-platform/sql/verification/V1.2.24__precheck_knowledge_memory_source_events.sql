-- 只读；知识/记忆源表必须存在，新outbox应不存在。
SELECT DATABASE() AS selected_schema;
SELECT table_name,engine FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('kb_knowledge_base','kb_index_release','kb_index_release_document','kb_document','kb_document_version','ai_memory_source','ai_memory_dependency','ai_memory_outbox');
SELECT COUNT(*) AS existing_knowledge_memory_outbox FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='kb_memory_source_outbox';
