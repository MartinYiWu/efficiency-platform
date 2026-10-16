ALTER TABLE ai_operation_artifact
    ADD COLUMN scenario VARCHAR(64) NULL AFTER artifact_type,
    ADD COLUMN root_artifact_id CHAR(36) NULL AFTER version_no,
    ADD COLUMN parent_artifact_id CHAR(36) NULL AFTER root_artifact_id,
    ADD COLUMN public_content JSON NULL AFTER body_html;

UPDATE ai_operation_artifact
SET scenario = artifact_type,
    root_artifact_id = id,
    public_content = JSON_OBJECT(
        'title', title,
        'body_markdown', body_markdown,
        'platform', platform
    )
WHERE root_artifact_id IS NULL;

ALTER TABLE ai_operation_artifact
    MODIFY COLUMN scenario VARCHAR(64) NOT NULL,
    MODIFY COLUMN root_artifact_id CHAR(36) NOT NULL,
    ADD UNIQUE KEY uk_ai_operation_artifact_root_version (root_artifact_id, version_no),
    ADD KEY idx_ai_operation_artifact_parent (parent_artifact_id);
