-- 只读：完整列约束及NONE异常成员；最后查询必须为空。
SELECT column_name,is_nullable,column_default FROM information_schema.columns
 WHERE table_schema=current_schema() AND table_name='agent_memory_thread_execution'
 AND column_name IN ('checkpoint_mode','root_thread_id');
SELECT k.conname,pg_get_constraintdef(k.oid) FROM pg_constraint k
 JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname=current_schema() AND c.relname='agent_memory_thread_execution'
 AND k.conname IN ('ck_memory_thread_checkpoint_mode','ck_memory_thread_checkpoint_owner');
SELECT e.tenant_id,e.execution_id,m.thread_id FROM agent_memory_thread_execution e
 JOIN agent_memory_thread_member m USING(tenant_id,execution_id) WHERE e.checkpoint_mode='NONE';
