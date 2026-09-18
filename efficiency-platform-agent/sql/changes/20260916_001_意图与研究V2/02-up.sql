BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='60s';
SELECT pg_advisory_xact_lock(hashtextextended('20260916_001_意图与研究V2', 0));

INSERT INTO agent_runtime.schema_changes
    (change_id,execution_mode,script_checksum,authorization_ref,executor,attempt,status)
VALUES
    ('20260916_001_意图与研究V2','external_controlled','x01-v2-reviewed-1',
     'user-2026-09-17-all-authorized',current_user,1,'running')
ON CONFLICT (change_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS agent_runtime.feature_controls (
    feature_name TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO agent_runtime.feature_controls(feature_name,enabled)
VALUES ('intent_research_v2_writes',TRUE)
ON CONFLICT (feature_name) DO NOTHING;

CREATE TABLE IF NOT EXISTS agent_runtime.intent_states (
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    revision BIGINT NOT NULL CHECK (revision > 0),
    frame JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,task_id)
);

CREATE TABLE IF NOT EXISTS agent_runtime.research_actions (
    tenant_id TEXT NOT NULL,
    research_id TEXT NOT NULL,
    action_fingerprint TEXT NOT NULL,
    invocation_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('IN_PROGRESS','COMMITTED','UNKNOWN_OUTCOME','CANCELLED','FAILED')),
    attempt INTEGER NOT NULL CHECK (attempt > 0),
    request JSONB NOT NULL,
    result JSONB,
    conservative_charge JSONB,
    provider_request_id TEXT,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,research_id,action_fingerprint),
    UNIQUE (tenant_id,research_id,invocation_id)
);

CREATE TABLE IF NOT EXISTS agent_runtime.research_decisions (
    tenant_id TEXT NOT NULL,
    research_id TEXT NOT NULL,
    decision_sequence BIGINT NOT NULL CHECK (decision_sequence > 0),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,research_id,decision_sequence)
);

CREATE TABLE IF NOT EXISTS agent_runtime.research_artifacts (
    tenant_id TEXT NOT NULL,
    research_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    artifact_kind TEXT NOT NULL CHECK (artifact_kind IN ('raw_html','evidence_excerpt','metadata')),
    payload JSONB NOT NULL,
    content_hash TEXT,
    source_retention_days INTEGER CHECK (source_retention_days IS NULL OR source_retention_days > 0),
    tenant_retention_days INTEGER CHECK (tenant_retention_days IS NULL OR tenant_retention_days > 0),
    expires_at TIMESTAMPTZ NOT NULL,
    expired_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,research_id,artifact_id)
);
CREATE INDEX IF NOT EXISTS research_artifacts_expiry_idx
ON agent_runtime.research_artifacts(expires_at)
WHERE expired_at IS NULL;

CREATE TABLE IF NOT EXISTS agent_runtime.budget_ledgers (
    ledger_key TEXT PRIMARY KEY,
    scope JSONB NOT NULL,
    limits JSONB NOT NULL,
    used JSONB NOT NULL,
    reserved JSONB NOT NULL,
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    terminal_reason TEXT CHECK (terminal_reason IN ('cancelled','terminal')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS agent_runtime.budget_reservations (
    reservation_id TEXT PRIMARY KEY,
    ledger_key TEXT NOT NULL REFERENCES agent_runtime.budget_ledgers(ledger_key),
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    quota_dimension TEXT NOT NULL,
    source_account_id TEXT,
    source_account_key TEXT GENERATED ALWAYS AS (COALESCE(source_account_id,'')) STORED,
    invocation_id TEXT NOT NULL,
    charge JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('reserved','dispatched','settled','released')),
    version BIGINT NOT NULL CHECK (version > 0),
    actual JSONB,
    outcome TEXT CHECK (outcome IS NULL OR outcome IN ('success','failed','cancelled','unknown')),
    settlement_late BOOLEAN NOT NULL DEFAULT FALSE,
    delivery_allowed BOOLEAN NOT NULL DEFAULT TRUE,
    over_limit BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (ledger_key,tenant_id,run_id,stage,quota_dimension,source_account_key,invocation_id)
);

CREATE TABLE IF NOT EXISTS agent_runtime.budget_usage (
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    quota_dimension TEXT NOT NULL,
    source_account_key TEXT NOT NULL DEFAULT '',
    used JSONB NOT NULL,
    reserved JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,run_id,stage,quota_dimension,source_account_key)
);

CREATE TABLE IF NOT EXISTS agent_runtime.checkpoints (
    thread_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    state JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,thread_id,checkpoint_ns)
);

UPDATE agent_runtime.schema_changes
SET status='succeeded',finished_at=clock_timestamp()
WHERE change_id='20260916_001_意图与研究V2';
COMMIT;

