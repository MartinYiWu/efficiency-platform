-- 受控人工回滚；仅全新未使用允许，不能删授权墓碑让旧投影复活。
DELIMITER $$
CREATE PROCEDURE assert_memory_sharing_unused()
BEGIN
 IF (SELECT COUNT(*) FROM ai_memory_sharing_scope)+(SELECT COUNT(*) FROM ai_memory_sharing_member)+(SELECT COUNT(*) FROM ai_memory_sharing_grant)+(SELECT COUNT(*) FROM ai_memory_sharing_projection)+(SELECT COUNT(*) FROM ai_memory_source WHERE source_type='MEMORY_SHARE_GRANT')>0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SHARING_ROLLBACK_REQUIRES_UNUSED'; END IF;
END$$
DELIMITER ;
CALL assert_memory_sharing_unused();
DROP PROCEDURE assert_memory_sharing_unused;
DROP TABLE ai_memory_sharing_projection;
DROP TABLE ai_memory_sharing_grant;
DROP TABLE ai_memory_sharing_member;
DROP TABLE ai_memory_sharing_scope;
