SELECT DATABASE() AS selected_schema;
SELECT COUNT(*) AS existing_semantic_tables FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='ai_memory_index_job';
SELECT COUNT(*) AS existing_semantic_triggers FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name LIKE 'trg_memory_index_%';
