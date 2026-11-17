-- 只允许新表从未使用且无墓碑；不修改旧 packet。拒绝时不移除任何保护。
SET SESSION lock_wait_timeout=5;
SET SESSION innodb_lock_wait_timeout=5;
DELIMITER $$
CREATE PROCEDURE rollback_memory_packet_refresh_v1218()
BEGIN
 IF EXISTS(SELECT 1 FROM ai_memory_packet_refresh) OR EXISTS(SELECT 1 FROM ai_memory_tombstone) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_REFRESH_ROLLBACK_REQUIRES_UNUSED';
 END IF;
 DROP TRIGGER trg_memory_packet_refresh_delete;
 DROP TRIGGER trg_memory_packet_refresh_update;
 DROP TRIGGER trg_memory_packet_refresh_insert;
 DROP TABLE ai_memory_packet_refresh;
END$$
DELIMITER ;
CALL rollback_memory_packet_refresh_v1218();
DROP PROCEDURE rollback_memory_packet_refresh_v1218;
