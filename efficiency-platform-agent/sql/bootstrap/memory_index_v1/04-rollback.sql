-- 先由部署配置关闭索引/召回开关并停止Worker；不回滚权威记忆或删除/付费历史。
BEGIN;
DO $$ BEGIN
 IF current_schema() !~ '^(agent_runtime(_[a-f0-9]{8})?|s7_acceptance_[a-f0-9]{8})$' THEN
   RAISE EXCEPTION 'Agent owned schema required';
 END IF;
END $$;
DELETE FROM memory_index_entries;
UPDATE memory_index_jobs SET state='DELETED' WHERE state='READY';
UPDATE memory_query_operations SET state=CASE WHEN state IN ('INFLIGHT','UNKNOWN') THEN state ELSE 'DELETED' END,embedding=NULL,item_refs='[]';
-- 保留fences、task slots以及INFLIGHT/UNKNOWN，不允许恢复旧upsert重新收费。
COMMIT;
