SELECT
    SUM(index_name = 'uk_ai_operation_artifact_version') AS legacy_index_count,
    SUM(index_name = 'uk_ai_operation_artifact_platform_version') AS platform_index_column_count
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'ai_operation_artifact'
  AND index_name IN (
      'uk_ai_operation_artifact_version',
      'uk_ai_operation_artifact_platform_version'
  );

SELECT conversation_id, artifact_type, platform, version_no, COUNT(*) AS duplicate_count
FROM ai_operation_artifact
GROUP BY conversation_id, artifact_type, platform, version_no
HAVING COUNT(*) > 1;
