SHOW CREATE TABLE agent_context_operation;
SHOW CREATE TABLE agent_context_manifest;
SELECT TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX,COLUMN_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('agent_context_manifest','agent_context_operation') ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX;
-- 应返回零行；不输出正文元数据。
SELECT tenant_id,task_id,execution_id,operation_id FROM agent_context_operation WHERE status NOT IN ('NOT_SENT','SENT','UNKNOWN','SUCCEEDED');
SELECT m.tenant_id,m.task_id,m.execution_id,m.operation_id FROM agent_context_manifest m LEFT JOIN agent_context_operation o ON m.tenant_id=o.tenant_id AND m.task_id=o.task_id AND m.execution_id=o.execution_id AND m.operation_id=o.operation_id WHERE o.operation_id IS NULL OR m.input_hash<>o.input_hash;

-- 应恰好8行，四类身份在两表均为VARBINARY(512)，无字符排序规则。
SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE,CHARACTER_OCTET_LENGTH,COLLATION_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('agent_context_manifest','agent_context_operation') AND COLUMN_NAME IN ('tenant_id','task_id','execution_id','operation_id') ORDER BY TABLE_NAME,ORDINAL_POSITION;
