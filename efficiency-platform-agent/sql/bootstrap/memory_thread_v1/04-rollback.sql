-- 仅未启用且本次新建的空四表允许人工在原schema执行；存在数据即拒绝。
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM agent_memory_thread_execution)
 OR EXISTS(SELECT 1 FROM agent_memory_thread_member)
 OR EXISTS(SELECT 1 FROM agent_memory_thread_namespace)
 OR EXISTS(SELECT 1 FROM agent_memory_thread_resume) THEN
  RAISE EXCEPTION 'MEMORY_THREAD_ROLLBACK_REQUIRES_UNUSED_EMPTY_TABLES';
 END IF;
END $$;
DROP TABLE agent_memory_thread_resume;
DROP TABLE agent_memory_thread_namespace;
DROP TABLE agent_memory_thread_member;
DROP TABLE agent_memory_thread_execution;
