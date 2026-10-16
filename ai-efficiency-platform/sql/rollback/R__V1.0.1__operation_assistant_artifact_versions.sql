ALTER TABLE ai_operation_artifact
    DROP INDEX uk_ai_operation_artifact_root_version,
    DROP INDEX idx_ai_operation_artifact_parent,
    DROP COLUMN public_content,
    DROP COLUMN parent_artifact_id,
    DROP COLUMN root_artifact_id,
    DROP COLUMN scenario;
