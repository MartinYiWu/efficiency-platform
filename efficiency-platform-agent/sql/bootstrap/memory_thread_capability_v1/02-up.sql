-- D16新增显式能力；仅专属技术schema经审核后在事务中执行。
ALTER TABLE agent_memory_thread_execution ADD COLUMN checkpoint_mode text NOT NULL DEFAULT 'GRAPH';
ALTER TABLE agent_memory_thread_execution ALTER COLUMN root_thread_id DROP NOT NULL;
ALTER TABLE agent_memory_thread_execution ADD CONSTRAINT ck_memory_thread_checkpoint_mode
 CHECK (checkpoint_mode IN ('GRAPH','NONE'));
ALTER TABLE agent_memory_thread_execution ADD CONSTRAINT ck_memory_thread_checkpoint_owner
 CHECK ((checkpoint_mode='GRAPH' AND root_thread_id IS NOT NULL AND root_thread_id=runtime_id
   AND jsonb_typeof(backend_ids)='array' AND jsonb_array_length(backend_ids)>0)
 OR (checkpoint_mode='NONE' AND root_thread_id IS NULL AND backend_ids='[]'::jsonb));
