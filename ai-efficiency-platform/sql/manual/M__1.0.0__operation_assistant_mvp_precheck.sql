-- 目标环境：开发环境 Java MySQL。
-- 影响数据库和表：只读检查当前 database 及四个 ai_operation_* 表。
-- 预估影响：无写入、无锁表。
-- 前置检查：确认连接的是本项目开发库，不是生产库。
-- 授权要求：由开发人员在执行 V1.0.0 前人工运行。
-- 执行窗口：迁移前。
-- 失败处理：发现同名表或版本冲突时停止执行并核对历史，禁止覆盖。
-- 回滚方式：只读脚本无需回滚。

SELECT DATABASE() AS target_database, VERSION() AS mysql_version;

SELECT table_name
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
      'ai_operation_conversation',
      'ai_operation_message',
      'ai_operation_run',
      'ai_operation_artifact'
  )
ORDER BY table_name;
