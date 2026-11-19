-- 人工受控；仅四表全部未用允许。MySQL DDL隐式提交；使用后严禁删除锚/墓碑后绕过。
DELIMITER $$
CREATE PROCEDURE assert_memory_summary_unused()
BEGIN
 IF (SELECT COUNT(*) FROM ai_memory_summary_watermark)+(SELECT COUNT(*) FROM ai_memory_summary_source)+(SELECT COUNT(*) FROM ai_memory_summary_plan)+(SELECT COUNT(*) FROM ai_memory_summary_segment)>0 THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SUMMARY_ROLLBACK_REQUIRES_UNUSED';
 END IF;
END$$
DELIMITER ;
CALL assert_memory_summary_unused();
DROP PROCEDURE assert_memory_summary_unused;
DROP TRIGGER trg_summary_source_invalidation;
DROP TABLE ai_memory_summary_segment;
DROP TABLE ai_memory_summary_plan;
DROP TABLE ai_memory_summary_source;
DROP TABLE ai_memory_summary_watermark;
