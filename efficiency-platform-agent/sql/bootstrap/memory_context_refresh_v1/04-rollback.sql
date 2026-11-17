-- 仅完全未使用增量。所有破坏性语句均位于硬拒绝之后的同一过程体；拒绝时不删除保护。
-- MySQL 过程中的 DDL 仍隐式提交，部分回滚须停用并人工恢复；拒绝可能留存此诊断过程。
SET SESSION lock_wait_timeout=5;
SET SESSION innodb_lock_wait_timeout=5;
DELIMITER $$
CREATE PROCEDURE rollback_memory_context_refresh_v1()
BEGIN
 IF EXISTS(SELECT 1 FROM agent_memory_context_refresh) OR EXISTS(SELECT 1 FROM agent_memory_execution WHERE NOT(current_context_fingerprint<=>context_fingerprint) OR state IN ('REVOKED','SCRUBBED')) OR EXISTS(SELECT 1 FROM agent_memory_invalidation_receipt) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_ROLLBACK_REQUIRES_UNUSED';
 END IF;
 DROP TRIGGER trg_memory_execution_refresh;
 DROP TRIGGER trg_memory_refresh_delete;
 DROP TRIGGER trg_memory_refresh_update;
 DROP TRIGGER trg_memory_refresh_insert;
 DROP TABLE agent_memory_context_refresh;
 ALTER TABLE agent_memory_execution DROP CHECK ck_memory_execution_current_fp,DROP COLUMN current_context_fingerprint;
END$$
DELIMITER ;
CALL rollback_memory_context_refresh_v1();
DROP PROCEDURE rollback_memory_context_refresh_v1;
