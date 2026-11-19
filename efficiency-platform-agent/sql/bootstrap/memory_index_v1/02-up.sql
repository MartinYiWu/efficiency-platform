BEGIN;
DO $$ BEGIN
 IF current_schema() !~ '^(agent_runtime(_[a-f0-9]{8})?|s7_acceptance_[a-f0-9]{8})$' THEN
   RAISE EXCEPTION 'Agent owned schema required';
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS memory_index_fences (
 scope_key TEXT NOT NULL, item_id TEXT NOT NULL, generation BIGINT NOT NULL CHECK(generation>=0),
 deletion_epoch BIGINT NOT NULL CHECK(deletion_epoch>=0), deleted BOOLEAN NOT NULL,
 forget_epoch BIGINT NOT NULL DEFAULT -1 CHECK(forget_epoch>=-1),
 PRIMARY KEY(scope_key,item_id));
CREATE TABLE IF NOT EXISTS memory_index_task_slots (
 tenant_id TEXT NOT NULL, task_id TEXT NOT NULL, operation_id TEXT NOT NULL UNIQUE,
 fingerprint TEXT NOT NULL, PRIMARY KEY(tenant_id,task_id));
CREATE TABLE IF NOT EXISTS memory_index_jobs (
 scope_key TEXT NOT NULL, embedding_model TEXT NOT NULL, dimension INTEGER NOT NULL CHECK(dimension BETWEEN 1 AND 4096),
 policy_version TEXT NOT NULL, item_id TEXT NOT NULL, generation BIGINT NOT NULL CHECK(generation>0),
 version_id TEXT NOT NULL, deletion_epoch BIGINT NOT NULL CHECK(deletion_epoch>=0),
 source_fingerprint TEXT NOT NULL CHECK(length(source_fingerprint)=64), fingerprint TEXT NOT NULL,
 token TEXT NOT NULL UNIQUE, state TEXT NOT NULL CHECK(state IN ('INFLIGHT','UNKNOWN','READY','DELETED')),
 operation_id TEXT NOT NULL, event_id TEXT NOT NULL, created_at BIGINT NOT NULL,
 PRIMARY KEY(scope_key,embedding_model,dimension,policy_version,item_id,generation));
CREATE TABLE IF NOT EXISTS memory_index_entries (
 scope_key TEXT NOT NULL, embedding_model TEXT NOT NULL, dimension INTEGER NOT NULL CHECK(dimension BETWEEN 1 AND 4096),
 policy_version TEXT NOT NULL, item_id TEXT NOT NULL, generation BIGINT NOT NULL CHECK(generation>0),
 version_id TEXT NOT NULL, deletion_epoch BIGINT NOT NULL CHECK(deletion_epoch>=0),
 source_fingerprint TEXT NOT NULL CHECK(length(source_fingerprint)=64),
 expires_at BIGINT NOT NULL CHECK(expires_at>0),
 embedding TEXT NOT NULL CHECK(jsonb_typeof(embedding::jsonb)='array' AND jsonb_array_length(embedding::jsonb)=dimension),
 terms TEXT NOT NULL CHECK(jsonb_typeof(terms::jsonb)='array' AND jsonb_array_length(terms::jsonb)<=32),
 PRIMARY KEY(scope_key,embedding_model,dimension,policy_version,item_id));
CREATE INDEX IF NOT EXISTS memory_index_jobs_pending ON memory_index_jobs(state,created_at);
CREATE TABLE IF NOT EXISTS memory_query_operations(
 tenant_id TEXT NOT NULL,task_id TEXT NOT NULL,scope_key TEXT NOT NULL,
 embedding_model TEXT NOT NULL,dimension INTEGER NOT NULL CHECK(dimension BETWEEN 1 AND 4096),policy_version TEXT NOT NULL,
 query_hash TEXT NOT NULL CHECK(length(query_hash)=64),fingerprint TEXT NOT NULL,token TEXT NOT NULL UNIQUE,
 state TEXT NOT NULL CHECK(state IN ('INFLIGHT','UNKNOWN','READY','DELETED')),operation_id TEXT NOT NULL,
 embedding TEXT CHECK(embedding IS NULL OR (jsonb_typeof(embedding::jsonb)='array' AND jsonb_array_length(embedding::jsonb)=dimension)),
 item_refs TEXT NOT NULL,created_at BIGINT NOT NULL,expires_at BIGINT NOT NULL CHECK(expires_at>0),PRIMARY KEY(tenant_id,task_id));
CREATE INDEX IF NOT EXISTS memory_index_entries_expiry ON memory_index_entries(expires_at,scope_key,item_id);
CREATE INDEX IF NOT EXISTS memory_query_operations_expiry ON memory_query_operations(expires_at,scope_key,task_id);
COMMIT;
