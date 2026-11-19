-- 只读结构/计数校验。
SELECT table_name,column_name,column_type,is_nullable FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name IN ('ai_memory_episode','ai_memory_episode_like','ai_memory_promotion') ORDER BY table_name,ordinal_position;
SELECT trigger_name,event_object_table,event_manipulation FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND (trigger_name LIKE 'trg_episode_%' OR trigger_name LIKE 'trg_promotion_%');
SELECT COUNT(*) AS invalid_shared FROM ai_memory_episode WHERE status='SHARED' AND (shared_payload IS NULL OR share_approver_id=owner_id);
SELECT COUNT(*) AS invalid_promotions FROM ai_memory_promotion WHERE status='PUBLISHED' AND (passed_cases<>total_cases OR total_cases=0 OR publisher_id=owner_id OR publisher_id=regression_reviewer_id);
SELECT COUNT(*) AS revoked_unscrubbed FROM ai_memory_episode WHERE status='REVOKED' AND (encrypted_payload IS NOT NULL OR shared_payload IS NOT NULL);
