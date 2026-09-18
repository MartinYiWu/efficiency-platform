-- 只读盘点 bootstrap、冲突对象和当前长事务；不得写会话持久状态。
SELECT current_database() AS database_name,
       current_user AS executor,
       EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='agent_runtime') AS schema_exists,
       to_regclass('agent_runtime.schema_changes') IS NOT NULL AS ledger_exists;

SELECT table_name
FROM information_schema.tables
WHERE table_schema='agent_runtime'
  AND table_name IN (
    'intent_states','research_actions','research_decisions','research_artifacts',
    'budget_ledgers','budget_reservations','budget_usage','checkpoints','feature_controls'
  )
ORDER BY table_name;

SELECT pid, xact_start, state
FROM pg_stat_activity
WHERE datname=current_database() AND xact_start IS NOT NULL AND pid <> pg_backend_pid()
ORDER BY xact_start;

