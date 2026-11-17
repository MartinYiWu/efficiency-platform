SHOW CREATE TABLE agent_context_stage;
-- 四类身份应为VARBINARY(512)，无字符排序规则；主键四列共2048字节。
SELECT COLUMN_NAME,DATA_TYPE,CHARACTER_OCTET_LENGTH,COLLATION_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='agent_context_stage' AND COLUMN_NAME IN ('tenant_id','task_id','execution_id','stage_id') ORDER BY ORDINAL_POSITION;
SELECT INDEX_NAME,SEQ_IN_INDEX,COLUMN_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='agent_context_stage' ORDER BY INDEX_NAME,SEQ_IN_INDEX;
-- 以下应返回零行，不读取Prompt或业务表。
SELECT tenant_id,task_id,execution_id,stage_id FROM agent_context_stage WHERE current_slot NOT BETWEEN 1 AND 3 OR status NOT IN ('CLAIMED','RETURNED','SUCCEEDED','INVALID','UNKNOWN') OR operation_id_1=operation_id_2 OR operation_id_1=operation_id_3 OR operation_id_2=operation_id_3;
