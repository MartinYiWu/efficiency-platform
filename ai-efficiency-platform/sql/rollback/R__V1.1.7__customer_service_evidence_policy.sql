-- 人工受控回滚，需独立授权。先回退应用并停止 /2 发布；保留已有 Release 快照。
-- 以下操作会丢失新策略字段和备选模型绑定，执行前备份两表。
-- 对应 migration/V1.1.7__customer_service_evidence_policy.sql；回滚后用同版本 verification 的列查询确认五列不存在。
ALTER TABLE ai_agent_version_policy_binding DROP COLUMN large_context_model_policy_id;
ALTER TABLE ai_rag_policy
    DROP COLUMN final_evidence_top_k,
    DROP COLUMN similarity_candidate_threshold,
    DROP COLUMN similarity_pair_limit,
    DROP COLUMN adjacent_group_max_parents;
-- Prompt 种子不在此删除：可能已被管理端发布/绑定；不得删除历史引用。
