-- 只读确认目标数据库与 agent_runtime 当前状态。
SELECT current_database() AS database_name,
       current_user AS executor,
       EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='agent_runtime') AS schema_exists;

SELECT n.nspname, c.relname, c.relkind
FROM pg_class c
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='agent_runtime'
ORDER BY c.relname;

