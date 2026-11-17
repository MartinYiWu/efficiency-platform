-- 只读检查，不读取正文或授权snapshot。
SHOW CREATE TABLE ai_memory_packet;
SELECT COUNT(*) AS invalid_deadlines FROM ai_memory_packet WHERE issued_at >= expires_at OR expires_at > original_deadline;
