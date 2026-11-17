-- 状态：D16候选；负责人：D16；2026-11-17。仅在专属技术schema经显式审核后执行。
CREATE TABLE agent_memory_thread_execution (
    tenant_id text NOT NULL,
    execution_id text NOT NULL,
    runtime_id text NOT NULL UNIQUE,
    root_thread_id text NOT NULL UNIQUE,
    scope jsonb NOT NULL,
    operation_hash text NOT NULL,
    execution_revision bigint NOT NULL CHECK (execution_revision >= 0),
    fence_revision bigint NOT NULL DEFAULT 0 CHECK (fence_revision >= 0),
    state text NOT NULL CHECK (state IN ('ACTIVE','BLOCKED','REVOKED','DELETED','EXPIRED')),
    dependencies jsonb NOT NULL,
    backend_ids jsonb NOT NULL,
    packet_revision bigint NOT NULL CHECK (packet_revision > 0),
    packet_expires_at bigint NOT NULL CHECK (packet_expires_at > 0),
    original_deadline bigint NOT NULL CHECK (original_deadline >= packet_expires_at),
    semantic_digest text NOT NULL,
    registry_complete boolean NOT NULL DEFAULT false,
    wait_event_id text,
    refresh_count integer NOT NULL DEFAULT 0 CHECK (refresh_count BETWEEN 0 AND 3),
    PRIMARY KEY (tenant_id, execution_id)
);
CREATE TABLE agent_memory_thread_member (
    thread_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    execution_id text NOT NULL,
    parent_thread_id text,
    dependencies jsonb NOT NULL,
    FOREIGN KEY (tenant_id, execution_id) REFERENCES agent_memory_thread_execution(tenant_id, execution_id),
    UNIQUE (tenant_id, execution_id, thread_id),
    FOREIGN KEY (tenant_id, execution_id, parent_thread_id)
        REFERENCES agent_memory_thread_member(tenant_id, execution_id, thread_id)
);
CREATE TABLE agent_memory_thread_namespace (
    thread_id text NOT NULL REFERENCES agent_memory_thread_member(thread_id),
    backend_id text NOT NULL,
    checkpoint_ns text NOT NULL,
    pending_writes boolean NOT NULL DEFAULT false,
    PRIMARY KEY (thread_id, backend_id, checkpoint_ns)
);
CREATE TABLE agent_memory_thread_resume (
    tenant_id text NOT NULL,
    execution_id text NOT NULL,
    resume_request_id text NOT NULL,
    request_hash text NOT NULL,
    result_code text NOT NULL,
    receipt_ref text NOT NULL,
    PRIMARY KEY (tenant_id, execution_id, resume_request_id),
    FOREIGN KEY (tenant_id, execution_id) REFERENCES agent_memory_thread_execution(tenant_id, execution_id)
);
