-- 只读，不输出加密快照或原输入。
SHOW CREATE TABLE agent_memory_execution;
SHOW CREATE TABLE agent_memory_invalidation_receipt;
SELECT state,COUNT(*) AS execution_count FROM agent_memory_execution GROUP BY state;
