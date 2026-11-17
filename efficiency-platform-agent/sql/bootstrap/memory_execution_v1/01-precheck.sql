-- 只读预检，不扩大目标Schema授权。
SELECT DATABASE() AS selected_schema, VERSION() AS mysql_version;
SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('agent_memory_execution','agent_memory_invalidation_receipt','agent_run');
