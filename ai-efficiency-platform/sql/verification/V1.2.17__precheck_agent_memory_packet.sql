-- 只读：目标须显式选定，结果不得用作共享DDL授权。
SELECT DATABASE() AS selected_schema, VERSION() AS mysql_version;
SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('ai_memory_packet','ai_memory_item','ai_memory_version','ai_memory_source','ai_memory_dependency');
