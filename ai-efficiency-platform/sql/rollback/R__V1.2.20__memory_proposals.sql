-- 人工受控；仅三个新表全空且没有PROPOSAL依赖时回滚，禁止删除机会锚重领。
DELIMITER $$
CREATE PROCEDURE assert_memory_proposals_unused()
BEGIN
 IF (SELECT COUNT(*) FROM ai_memory_proposal)+(SELECT COUNT(*) FROM ai_memory_proposal_batch)+(SELECT COUNT(*) FROM ai_memory_proposal_source_claim)+(SELECT COUNT(*) FROM ai_memory_dependency WHERE target_type='PROPOSAL')>0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='PROPOSAL_ROLLBACK_REQUIRES_UNUSED'; END IF;
END$$
DELIMITER ;
CALL assert_memory_proposals_unused();
DROP PROCEDURE assert_memory_proposals_unused;
DROP TRIGGER trg_proposal_suppression_update;
DROP TRIGGER trg_proposal_suppression_insert;
DROP TRIGGER trg_proposal_source_invalidation;
DROP TABLE ai_memory_proposal;
DROP TABLE ai_memory_proposal_source_claim;
DROP TABLE ai_memory_proposal_batch;
