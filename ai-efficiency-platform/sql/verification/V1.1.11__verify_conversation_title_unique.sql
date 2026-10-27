-- 迁移前：应确认目标库和既有字段，历史重名修复后 duplicate_groups 必须为零。
SELECT DATABASE() AS database_name;
SELECT COUNT(*) AS duplicate_groups
FROM (
    SELECT tenant_id, user_id, LOWER(TRIM(title)) AS normalized_title
    FROM ai_customer_service_conversation
    WHERE status <> 'DELETED' AND CHAR_LENGTH(TRIM(COALESCE(title, ''))) > 0
    GROUP BY tenant_id, user_id, LOWER(TRIM(title))
    HAVING COUNT(*) > 1
) duplicates;

-- 迁移后：应存在生成列和完整的唯一索引，且 NON_UNIQUE 为零。
SELECT COLUMN_NAME, COLUMN_TYPE, EXTRA, GENERATION_EXPRESSION
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_customer_service_conversation'
  AND COLUMN_NAME = 'title_unique_key';
SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_customer_service_conversation'
  AND INDEX_NAME = 'uk_ai_cs_conversation_title'
ORDER BY SEQ_IN_INDEX;
