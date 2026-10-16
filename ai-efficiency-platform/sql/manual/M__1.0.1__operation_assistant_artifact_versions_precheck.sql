SELECT DATABASE() AS target_database;
SELECT column_name FROM information_schema.columns
WHERE table_schema = DATABASE() AND table_name = 'ai_operation_artifact'
  AND column_name IN ('scenario','root_artifact_id','parent_artifact_id','public_content');
