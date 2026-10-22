-- 只读验证；历史空值允许存在，不得为验证目的回填。
SELECT column_name, column_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = DATABASE() AND table_name = 'kb_document_version'
  AND column_name = 'evidence_mode';

SELECT evidence_mode, COUNT(*) AS version_count
FROM kb_document_version GROUP BY evidence_mode;

SELECT COUNT(*) AS invalid_mode_count
FROM kb_document_version
WHERE evidence_mode IS NOT NULL AND evidence_mode NOT IN ('FULL_ONLY', 'EXTRACTIVE_NARRATIVE');
