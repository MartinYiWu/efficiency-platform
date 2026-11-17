SELECT DATABASE() AS selected_schema, VERSION() AS mysql_version;
SELECT table_name,column_name,is_nullable,column_type FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name IN ('agent_memory_execution','agent_memory_invalidation_receipt') ORDER BY table_name,ordinal_position;
SELECT state,COUNT(*) AS row_count FROM agent_memory_execution GROUP BY state;
SELECT COUNT(*) AS invalid_bodies FROM agent_memory_execution WHERE snapshot_ciphertext IS NULL OR snapshot_nonce IS NULL;
SELECT trigger_name FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND event_object_table='agent_memory_execution';
