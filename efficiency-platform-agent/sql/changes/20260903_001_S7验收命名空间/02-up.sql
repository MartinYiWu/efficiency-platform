-- S7 Agent 自有验收 Schema；执行前必须完成只读预检和写入授权。
CREATE SCHEMA s7_acceptance_00000000;

CREATE TABLE s7_acceptance_00000000.runs (
    run_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    request_id TEXT,
    payload JSONB NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE s7_acceptance_00000000.run_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, tenant_id, sequence)
);

CREATE TABLE s7_acceptance_00000000.run_usage (
    run_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    cost_microunits BIGINT NOT NULL DEFAULT 0 CHECK (cost_microunits >= 0)
);

CREATE TABLE s7_acceptance_00000000.checkpoints (
    thread_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    state JSONB NOT NULL,
    saved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (thread_id, tenant_id, checkpoint_ns)
);

CREATE TABLE s7_acceptance_00000000.chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1024) NOT NULL,
    embedding_model TEXT NOT NULL CHECK (embedding_model = 'text-embedding-v4'),
    embedding_dimension INTEGER NOT NULL CHECK (embedding_dimension = 1024)
);

CREATE INDEX chunks_embedding_hnsw_idx
    ON s7_acceptance_00000000.chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_content_fts_idx
    ON s7_acceptance_00000000.chunks USING gin (to_tsvector('simple', content));
