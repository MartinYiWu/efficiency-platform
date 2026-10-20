-- 对应迁移：V1.1.5__align_customer_service_runtime_columns.sql。
-- 回滚会丢失消息运行状态与会话末次消息时间，仅限确认无依赖后人工执行。

ALTER TABLE ai_customer_service_message
    DROP COLUMN status;

ALTER TABLE ai_customer_service_conversation
    DROP INDEX idx_ai_cs_conversation_last_message,
    DROP COLUMN last_message_at;
