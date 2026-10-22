-- 只读验证；空值为历史兼容状态，不要求回填。
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'customer_service' AND table_name = 'document_parent'
  AND column_name IN ('block_kind', 'evidence_mode');

SELECT block_kind, evidence_mode, COUNT(*) AS parent_count
FROM customer_service.document_parent GROUP BY block_kind, evidence_mode;

SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'customer_service.document_parent'::regclass
  AND conname IN ('ck_customer_service_parent_block_kind', 'ck_customer_service_parent_evidence_mode');
