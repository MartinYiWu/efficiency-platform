-- 人工受控；仅未用新表且无EPISODE依赖时允许回滚。
DELIMITER $$
CREATE PROCEDURE assert_memory_episodes_unused()
BEGIN
 IF (SELECT COUNT(*) FROM ai_memory_episode)+(SELECT COUNT(*) FROM ai_memory_episode_like)+(SELECT COUNT(*) FROM ai_memory_promotion)+(SELECT COUNT(*) FROM ai_memory_dependency WHERE target_type='EPISODE')>0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EPISODE_ROLLBACK_REQUIRES_UNUSED'; END IF;
END$$
DELIMITER ;
CALL assert_memory_episodes_unused();
DROP PROCEDURE assert_memory_episodes_unused;
DROP TRIGGER trg_episode_source_invalidation;
DROP TRIGGER trg_episode_revoke;
DROP TABLE ai_memory_promotion;
DROP TABLE ai_memory_episode_like;
DROP TABLE ai_memory_episode;
