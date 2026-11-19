-- 只读；不输出正文、登录引用或凭据。
SELECT DATABASE() AS selected_schema;
SELECT table_name,engine FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('ai_memory_item','ai_memory_version','ai_memory_source','ai_memory_dependency','ai_memory_outbox');
SELECT COUNT(*) AS sharing_tables_already_exist FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name LIKE 'ai_memory_sharing_%';
SELECT trigger_name,event_object_table FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name LIKE 'trg_sharing_%';
