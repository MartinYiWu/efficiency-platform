-- 只读核验四表、owner/runtime唯一约束、成员归属及回执复合外键。
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema=current_schema() AND table_name IN (
 'agent_memory_thread_execution','agent_memory_thread_member',
 'agent_memory_thread_namespace','agent_memory_thread_resume')
ORDER BY table_name, ordinal_position;
SELECT c.relname, k.conname, k.contype, pg_get_constraintdef(k.oid) AS definition
FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname=current_schema() AND c.relname IN (
 'agent_memory_thread_execution','agent_memory_thread_member',
 'agent_memory_thread_namespace','agent_memory_thread_resume')
ORDER BY c.relname,k.conname;
SELECT m.thread_id FROM agent_memory_thread_member m
JOIN agent_memory_thread_execution e USING(tenant_id,execution_id)
WHERE m.parent_thread_id IS NULL AND m.thread_id<>e.root_thread_id;
