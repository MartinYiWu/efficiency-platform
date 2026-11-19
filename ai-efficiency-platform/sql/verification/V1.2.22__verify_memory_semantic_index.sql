SELECT table_name,column_name,column_type,is_nullable FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='ai_memory_index_job' ORDER BY ordinal_position;
SELECT trigger_name,action_statement FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name LIKE 'trg_memory_index_%';
SELECT COUNT(*) AS invalid_memory_index_jobs FROM ai_memory_index_job WHERE generation<1 OR dimension NOT BETWEEN 1 AND 4096 OR state NOT IN ('QUEUED','SENDING','READY','UNKNOWN','DELETE_PENDING','DELETED');

SELECT COUNT(*) AS invalid_index_delete_receipts FROM ai_memory_index_job WHERE (state='DELETED' AND delete_receipt_ref IS NULL) OR (state<>'DELETED' AND delete_receipt_ref IS NOT NULL) OR delete_epoch<deletion_epoch;
