-- 同hash原始解析复用索引；只保存原件不可逆SHA-256，不回填既有材料。
ALTER TABLE ai_hr_source_authorization ADD COLUMN content_hash CHAR(64) NULL;
CREATE INDEX idx_hr_source_content_hash ON ai_hr_source_authorization(tenant_id,content_hash,candidate_id);
