-- 只读Schema/refs数量，不查正文或凭据。
SELECT column_name,column_type,is_nullable FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='kb_memory_source_outbox' ORDER BY ordinal_position;
SELECT status,COUNT(*) AS event_count FROM kb_memory_source_outbox GROUP BY status;
SELECT COUNT(*) AS invalid_events FROM kb_memory_source_outbox WHERE status NOT IN ('PENDING','DELIVERED') OR reason NOT IN ('INDEX_RELEASE_CHANGED','BASE_POLICY_CHANGED','DOCUMENT_STATE_CHANGED');
