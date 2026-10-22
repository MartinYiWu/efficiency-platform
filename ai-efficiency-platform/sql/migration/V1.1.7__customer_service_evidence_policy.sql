-- 状态：离线待预检；日期：2026-10-22；适用：Java MySQL 管理库。
-- 执行前必须核验 SELECT VERSION()、真实迁移历史及 V1.1.7 未使用，并获得单独授权。
-- 不回填历史已发布策略。NULL 表示旧策略，发布 /2 前必须创建带完整字段的新策略版本。
-- 所属 AI Hub；回滚：../rollback/R__V1.1.7__customer_service_evidence_policy.sql。
ALTER TABLE ai_rag_policy
    ADD COLUMN final_evidence_top_k INT NULL COMMENT '最终独立父证据数量，1-20，新策略默认8',
    ADD COLUMN similarity_candidate_threshold DECIMAL(20,18) NULL COMMENT '仅筛相似候选对，0.85-1，新策略默认0.96',
    ADD COLUMN similarity_pair_limit INT NULL COMMENT '相似候选对上限，1-50，新策略默认20',
    ADD COLUMN adjacent_group_max_parents INT NULL COMMENT '相邻组父片段数量，1-5，新策略默认3';

ALTER TABLE ai_agent_version_policy_binding
    ADD COLUMN large_context_model_policy_id CHAR(36) NULL COMMENT '可选已发布大上下文模型策略，必须同归属且输入上限更大';
