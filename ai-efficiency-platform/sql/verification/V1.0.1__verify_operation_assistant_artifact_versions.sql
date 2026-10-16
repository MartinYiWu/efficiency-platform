SELECT column_name, is_nullable, data_type
FROM information_schema.columns
WHERE table_schema = DATABASE() AND table_name = 'ai_operation_artifact'
  AND column_name IN ('scenario','root_artifact_id','parent_artifact_id','public_content')
ORDER BY ordinal_position;

SELECT COUNT(*) AS invalid_version_rows
FROM ai_operation_artifact
WHERE scenario IS NULL OR root_artifact_id IS NULL OR version_no < 1;

SELECT root_artifact_id, version_no, COUNT(*) AS duplicate_count
FROM ai_operation_artifact
GROUP BY root_artifact_id, version_no
HAVING COUNT(*) > 1;
