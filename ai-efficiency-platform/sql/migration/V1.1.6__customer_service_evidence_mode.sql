-- 仅新增可空元数据，不回填或重写历史文档版本；旧值由读取端按 FULL_ONLY 解释。
-- 执行前需核验迁移历史和 kb_document_version 结构，并取得数据库变更授权。
ALTER TABLE kb_document_version
    ADD COLUMN evidence_mode VARCHAR(32) NULL COMMENT '冻结证据模式；历史空值按 FULL_ONLY 读取',
    ADD CONSTRAINT ck_kb_document_version_evidence_mode
        CHECK (evidence_mode IS NULL OR evidence_mode IN ('FULL_ONLY', 'EXTRACTIVE_NARRATIVE'));
