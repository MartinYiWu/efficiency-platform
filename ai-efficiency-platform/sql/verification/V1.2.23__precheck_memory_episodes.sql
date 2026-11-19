-- 只读；不输出案例/Prompt正文或凭据。
SELECT DATABASE() AS selected_schema;
SELECT table_name,engine FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('ai_memory_packet','ai_memory_source','ai_memory_dependency','ai_memory_sharing_scope','ai_memory_policy_version');
SELECT COUNT(*) AS existing_episode_tables FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('ai_memory_episode','ai_memory_episode_like','ai_memory_promotion');
SELECT trigger_name,event_object_table FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND (trigger_name LIKE 'trg_episode_%' OR trigger_name LIKE 'trg_promotion_%');
