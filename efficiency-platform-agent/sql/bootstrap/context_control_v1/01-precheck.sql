-- 仅供授权后在指定 Agent 自有 MySQL 库执行。
SELECT DATABASE() AS current_database, VERSION() AS mysql_version;
SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('agent_context_manifest','agent_context_operation');
-- 若任一表已存在，停止并审阅结构，禁止自动覆盖。
SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('agent_context_manifest','agent_context_operation') ORDER BY TABLE_NAME,ORDINAL_POSITION;
