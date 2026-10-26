-- 预期四项 count 均为 0；任意对象已存在时先确认是否已执行过本迁移。
SELECT table_name
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
    'ai_rag_eval_dataset',
    'ai_rag_eval_case',
    'ai_rag_eval_run',
    'ai_rag_eval_case_result'
  );
