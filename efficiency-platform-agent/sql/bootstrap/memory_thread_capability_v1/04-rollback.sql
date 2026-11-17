-- 仅未使用的增量可人工回滚；不得删除NONE墓碑。
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM agent_memory_thread_execution WHERE checkpoint_mode='NONE') THEN
  RAISE EXCEPTION 'MEMORY_THREAD_CAPABILITY_ROLLBACK_REQUIRES_UNUSED_NONE_MODE';
 END IF;
END $$;
ALTER TABLE agent_memory_thread_execution DROP CONSTRAINT ck_memory_thread_checkpoint_owner;
ALTER TABLE agent_memory_thread_execution DROP CONSTRAINT ck_memory_thread_checkpoint_mode;
ALTER TABLE agent_memory_thread_execution ALTER COLUMN root_thread_id SET NOT NULL;
ALTER TABLE agent_memory_thread_execution DROP COLUMN checkpoint_mode;
