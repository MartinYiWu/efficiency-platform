-- 人工受控回滚：先回退应用，确认允许丢失新增证据模式元数据，再授权执行。
ALTER TABLE kb_document_version
    DROP CHECK ck_kb_document_version_evidence_mode,
    DROP COLUMN evidence_mode;
