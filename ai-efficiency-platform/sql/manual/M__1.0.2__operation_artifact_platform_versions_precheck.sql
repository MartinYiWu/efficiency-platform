SELECT index_name, GROUP_CONCAT(column_name ORDER BY seq_in_index) AS indexed_columns
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'ai_operation_artifact'
  AND index_name IN (
      'uk_ai_operation_artifact_version',
      'uk_ai_operation_artifact_platform_version',
      'uk_ai_operation_artifact_root_version'
  )
GROUP BY index_name;

SELECT conversation_id, artifact_type, platform, version_no, COUNT(*) AS duplicate_count
FROM ai_operation_artifact
GROUP BY conversation_id, artifact_type, platform, version_no
HAVING COUNT(*) > 1;
