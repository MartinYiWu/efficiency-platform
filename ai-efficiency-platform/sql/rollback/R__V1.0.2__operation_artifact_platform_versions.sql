-- 回滚前必须确认不存在跨平台的同类型同版本数据，否则恢复旧索引会失败。
ALTER TABLE ai_operation_artifact
    DROP INDEX uk_ai_operation_artifact_platform_version,
    ADD UNIQUE KEY uk_ai_operation_artifact_version
        (conversation_id, artifact_type, version_no);
