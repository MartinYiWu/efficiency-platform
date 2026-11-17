-- 只读：原四表须存在，checkpoint_mode须不存在，violations须为0。
SELECT current_schema(), to_regclass('agent_memory_thread_execution'),to_regclass('agent_memory_thread_member'),
 to_regclass('agent_memory_thread_namespace'),to_regclass('agent_memory_thread_resume');
SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema()
 AND table_name='agent_memory_thread_execution' AND column_name='checkpoint_mode';
SELECT count(*) AS violations FROM agent_memory_thread_execution
 WHERE root_thread_id<>runtime_id OR jsonb_typeof(backend_ids)<>'array' OR jsonb_array_length(backend_ids)=0;
