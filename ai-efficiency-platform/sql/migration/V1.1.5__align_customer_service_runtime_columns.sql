-- 所属模块：aiep-biz-aihub / AI 智能客服会话。
-- 影响表：ai_customer_service_conversation、ai_customer_service_message。
-- 前置核验：V1.1.0 已执行，且两张表存在。
-- 兼容性：仅新增可空时间列和带默认值的状态列，兼容已有数据与旧查询。
-- 数据回填：历史消息状态统一回填为 COMPLETED；历史会话 last_message_at 保持 NULL。
-- 回滚：rollback/R__V1.1.5__align_customer_service_runtime_columns.sql。

ALTER TABLE ai_customer_service_conversation
    ADD COLUMN last_message_at DATETIME(6) NULL AFTER last_agent_release_id,
    ADD KEY idx_ai_cs_conversation_last_message (tenant_id, user_id, last_message_at);

ALTER TABLE ai_customer_service_message
    ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED' AFTER content_markdown;
