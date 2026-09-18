SELECT change_id,status
FROM agent_runtime.schema_changes
WHERE change_id='20260916_001_意图与研究V2' AND status='succeeded';

SELECT table_name
FROM information_schema.tables
WHERE table_schema='agent_runtime'
  AND table_name IN (
    'intent_states','research_actions','research_decisions','research_artifacts',
    'budget_ledgers','budget_reservations','budget_usage','checkpoints','feature_controls'
  )
ORDER BY table_name;

SELECT conrelid::regclass::text AS relation_name, conname, contype
FROM pg_constraint
WHERE connamespace='agent_runtime'::regnamespace
ORDER BY relation_name,conname;

