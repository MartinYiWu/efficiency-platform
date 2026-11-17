-- 人工受控破坏性回滚；须关闭记忆、停止在途执行并单独确认目标Schema。
DROP TABLE agent_memory_invalidation_receipt;
DROP TABLE agent_memory_execution;
