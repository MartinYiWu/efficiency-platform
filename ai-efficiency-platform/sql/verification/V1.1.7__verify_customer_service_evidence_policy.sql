-- 只读预检/验证。先核验实际迁移历史；未启用自动迁移，不推测历史表名称。
SELECT VERSION() AS mysql_version;
SELECT table_name, column_name, column_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND ((table_name = 'ai_rag_policy' AND column_name IN
       ('final_evidence_top_k','similarity_candidate_threshold','similarity_pair_limit','adjacent_group_max_parents'))
    OR (table_name = 'ai_agent_version_policy_binding' AND column_name = 'large_context_model_policy_id'));
-- 迁移后执行：历史行允许全部 NULL；新行必须四字段完整并在范围内。
SELECT id, policy_key, semantic_version
FROM ai_rag_policy
WHERE (final_evidence_top_k IS NOT NULL OR similarity_candidate_threshold IS NOT NULL
    OR similarity_pair_limit IS NOT NULL OR adjacent_group_max_parents IS NOT NULL)
  AND (final_evidence_top_k IS NULL OR final_evidence_top_k NOT BETWEEN 1 AND 20
    OR similarity_candidate_threshold IS NULL OR similarity_candidate_threshold NOT BETWEEN 0.85 AND 1
    OR similarity_pair_limit IS NULL OR similarity_pair_limit NOT BETWEEN 1 AND 50
    OR adjacent_group_max_parents IS NULL OR adjacent_group_max_parents NOT BETWEEN 1 AND 5);
