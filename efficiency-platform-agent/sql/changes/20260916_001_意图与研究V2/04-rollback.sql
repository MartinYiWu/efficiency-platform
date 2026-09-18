BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
-- 回滚只停止新写；V2 记录、证据、Checkpoint 和旧读能力全部保留。
UPDATE agent_runtime.feature_controls
SET enabled=FALSE,updated_at=clock_timestamp()
WHERE feature_name='intent_research_v2_writes';
COMMIT;

