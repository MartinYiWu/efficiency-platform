ALTER TABLE ai_operation_artifact
    DROP INDEX uk_ai_operation_artifact_version,
    ADD UNIQUE KEY uk_ai_operation_artifact_platform_version
        (conversation_id, artifact_type, platform, version_no);
