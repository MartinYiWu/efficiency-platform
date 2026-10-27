-- 回滚前停用新版本标题写入，确认需要恢复原约束。
ALTER TABLE ai_customer_service_conversation
    DROP INDEX uk_ai_cs_conversation_title,
    DROP COLUMN title_unique_key;
-- 若需恢复历史重名，随后按迁移前本地备份中的 id 与原始 title 参数化更新。
-- 不在可提交 SQL 中保存任何实际用户标题或其他数据。
