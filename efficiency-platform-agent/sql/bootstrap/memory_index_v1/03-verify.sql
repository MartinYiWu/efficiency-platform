SELECT table_name,column_name,data_type FROM information_schema.columns
 WHERE table_schema=current_schema() AND table_name LIKE 'memory_index_%' ORDER BY table_name,ordinal_position;
SELECT COUNT(*) AS invalid_dimension FROM memory_index_entries
 WHERE jsonb_array_length(embedding::jsonb)<>dimension;
SELECT COUNT(*) AS expired_retention_entries FROM memory_index_entries
 WHERE expires_at<=EXTRACT(EPOCH FROM now())::BIGINT;
SELECT COUNT(*) AS stale_entries FROM memory_index_entries e JOIN memory_index_fences f
 ON e.scope_key=f.scope_key AND e.item_id=f.item_id
 WHERE f.deleted OR e.generation<>f.generation OR e.deletion_epoch<>f.deletion_epoch;
SELECT COUNT(*) AS unresolved_over_24h FROM memory_index_jobs
 WHERE state IN ('INFLIGHT','UNKNOWN') AND created_at<EXTRACT(EPOCH FROM now())::BIGINT-86400;
SELECT COUNT(*) AS unresolved_query_over_24h FROM memory_query_operations
 WHERE state IN ('INFLIGHT','UNKNOWN') AND created_at<EXTRACT(EPOCH FROM now())::BIGINT-86400;
SELECT COUNT(*) AS expired_query_payloads FROM memory_query_operations
 WHERE expires_at<=EXTRACT(EPOCH FROM now())::BIGINT AND (embedding IS NOT NULL OR item_refs<>'[]');
