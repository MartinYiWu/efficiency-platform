-- 对应迁移：V1.0.0__operation_assistant_mvp.sql
-- 不可逆风险：下列操作永久删除全部运营助手会话、消息、运行和制品数据。
-- 执行前条件：仅在明确放弃该迁移且数据已备份后人工执行；禁止在生产环境直接执行。
-- 执行后核验：查询 information_schema.tables，确认四张表均不存在。

DROP TABLE IF EXISTS ai_operation_artifact;
DROP TABLE IF EXISTS ai_operation_run;
DROP TABLE IF EXISTS ai_operation_message;
DROP TABLE IF EXISTS ai_operation_conversation;
