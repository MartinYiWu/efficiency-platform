SELECT nspname FROM pg_namespace WHERE nspname='agent_runtime';
SELECT change_id,execution_mode,status
FROM agent_runtime.schema_changes
WHERE change_id='agent_database_bootstrap_v1';

