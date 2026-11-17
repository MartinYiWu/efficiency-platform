-- 停止复用入口且确认授权后由root统一执行。
DROP INDEX idx_hr_source_content_hash ON ai_hr_source_authorization;
ALTER TABLE ai_hr_source_authorization DROP COLUMN content_hash;
