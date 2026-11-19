-- 受控人工回滚，仅新outbox完全未用允许，使用后保留送达锚不可删除重放。
DELIMITER $$
CREATE PROCEDURE assert_knowledge_memory_outbox_unused()
BEGIN
 IF (SELECT COUNT(*) FROM kb_memory_source_outbox)>0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='KNOWLEDGE_MEMORY_OUTBOX_ROLLBACK_REQUIRES_UNUSED'; END IF;
END$$
DELIMITER ;
CALL assert_knowledge_memory_outbox_unused();
DROP PROCEDURE assert_knowledge_memory_outbox_unused;
DROP TABLE kb_memory_source_outbox;
