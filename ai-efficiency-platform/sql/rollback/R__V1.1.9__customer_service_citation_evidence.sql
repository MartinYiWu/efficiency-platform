-- 人工受控回滚；先停用写入并回退应用。含新引用事实时拒绝丢列，须先单独审核备份/保留策略。
-- 对应 V1.1.9__customer_service_citation_evidence.sql；成功后用 information_schema.COLUMNS 确认三列均不存在。
DELIMITER //
CREATE PROCEDURE rollback_customer_service_citation_evidence()
BEGIN
    IF EXISTS (SELECT 1 FROM ai_customer_service_citation
               WHERE parent_id IS NOT NULL OR citation_type IS NOT NULL OR original_spans_json IS NOT NULL) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Citation evidence exists; rollback refused';
    END IF;
    ALTER TABLE ai_customer_service_citation
        DROP COLUMN original_spans_json, DROP COLUMN citation_type, DROP COLUMN parent_id;
END//
DELIMITER ;
CALL rollback_customer_service_citation_evidence();
DROP PROCEDURE rollback_customer_service_citation_evidence;
