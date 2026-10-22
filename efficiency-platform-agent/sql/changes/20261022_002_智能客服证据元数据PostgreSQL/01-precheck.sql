-- 只读预检：确认父片段表已存在，新列尚不存在，并评估 DDL 锁窗口。
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'customer_service' AND table_name = 'document_parent'
ORDER BY ordinal_position;

SELECT COUNT(*) AS parent_count FROM customer_service.document_parent;

SELECT relation::regclass, mode, granted
FROM pg_locks WHERE relation = 'customer_service.document_parent'::regclass;
