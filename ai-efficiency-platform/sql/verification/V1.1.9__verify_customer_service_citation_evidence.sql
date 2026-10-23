-- 只读核验；不展示引用正文。
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_customer_service_citation'
AND COLUMN_NAME IN ('parent_id','citation_type','original_spans_json');
SELECT COUNT(*) AS invalid_types FROM ai_customer_service_citation
WHERE citation_type IS NOT NULL AND citation_type NOT IN ('FULL_PARENT','EXTRACTED_SPANS');
SELECT COUNT(*) AS invalid_excerpts FROM ai_customer_service_citation
WHERE citation_type = 'EXTRACTED_SPANS' AND
(parent_id IS NULL OR original_spans_json IS NULL OR JSON_TYPE(original_spans_json) <> 'ARRAY' OR JSON_LENGTH(original_spans_json) = 0);
