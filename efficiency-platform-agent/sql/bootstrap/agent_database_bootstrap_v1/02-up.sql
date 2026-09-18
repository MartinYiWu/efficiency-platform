BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
SELECT pg_advisory_xact_lock(7887332933888385649);

CREATE SCHEMA IF NOT EXISTS agent_runtime;
CREATE TABLE IF NOT EXISTS agent_runtime.schema_changes (
    change_id TEXT PRIMARY KEY,
    execution_mode TEXT NOT NULL CHECK (execution_mode IN ('alembic_embedded','external_controlled')),
    script_checksum TEXT NOT NULL,
    authorization_ref TEXT NOT NULL,
    executor TEXT NOT NULL,
    attempt INTEGER NOT NULL CHECK (attempt > 0),
    status TEXT NOT NULL CHECK (status IN ('claimed','running','succeeded','failed')),
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at TIMESTAMPTZ
);
INSERT INTO agent_runtime.schema_changes
    (change_id,execution_mode,script_checksum,authorization_ref,executor,attempt,status,finished_at)
VALUES
    ('agent_database_bootstrap_v1','external_controlled','bootstrap-v1-reviewed',
     'user-2026-09-17-all-authorized',current_user,1,'succeeded',clock_timestamp())
ON CONFLICT (change_id) DO NOTHING;
COMMIT;

