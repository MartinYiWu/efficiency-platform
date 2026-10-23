-- 先执行只读预检并取得明确授权；不回填不可变历史运行。
ALTER TABLE agent_customer_service_retrieval_snapshot
    ADD COLUMN retrieval_facts_json JSON NULL
    COMMENT '最终父候选、相邻组、冲突结论及装配排除原因；旧运行为空';
