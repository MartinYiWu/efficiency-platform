-- Used jobs/financial opportunities cannot be reset by rollback.
DELIMITER $$
CREATE PROCEDURE memory_index_unused_rollback()
BEGIN
 IF EXISTS(SELECT 1 FROM ai_memory_index_job) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='MEMORY_INDEX_USED_ROLLBACK_FORBIDDEN'; END IF;
 DROP TRIGGER trg_memory_index_source_revoke;
 DROP TRIGGER trg_memory_index_version_revoke;
 DROP TRIGGER trg_memory_index_job_insert;
 DROP TRIGGER trg_memory_index_job_update;
 DROP TRIGGER trg_memory_index_job_delete;
 DROP TABLE ai_memory_index_job;
END$$
DELIMITER ;
CALL memory_index_unused_rollback();
DROP PROCEDURE memory_index_unused_rollback;
