-- 保留旧索引数据，父子关联仅由新摄取写入。
CREATE TABLE customer_service.document_parent (
    parent_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    knowledge_base_id UUID NOT NULL,
    document_id UUID NOT NULL,
    document_version_id UUID NOT NULL,
    document_title TEXT NOT NULL CHECK (length(btrim(document_title)) > 0),
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    parent_no INTEGER NOT NULL CHECK (parent_no > 0),
    section_path TEXT,
    page_start INTEGER CHECK (page_start IS NULL OR page_start > 0),
    page_end INTEGER CHECK (page_end IS NULL OR page_end > 0),
    content TEXT NOT NULL CHECK (length(btrim(content)) > 0),
    content_hash CHAR(64) NOT NULL,
    token_count INTEGER NOT NULL CHECK (token_count > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_version_id, parent_no),
    UNIQUE (parent_id, document_version_id)
);

CREATE INDEX idx_customer_service_parent_scope
    ON customer_service.document_parent
    (tenant_id, knowledge_base_id, document_version_id);

ALTER TABLE customer_service.document_chunk
    ADD COLUMN parent_id UUID,
    ADD COLUMN child_no INTEGER CHECK (child_no IS NULL OR child_no > 0),
    ADD COLUMN start_offset INTEGER CHECK (start_offset IS NULL OR start_offset >= 0),
    ADD COLUMN end_offset INTEGER CHECK (end_offset IS NULL OR end_offset > 0),
    ADD CONSTRAINT fk_customer_service_child_parent_version
        FOREIGN KEY (parent_id, document_version_id)
        REFERENCES customer_service.document_parent (parent_id, document_version_id),
    ADD CONSTRAINT ck_customer_service_child_position
        CHECK (start_offset IS NULL OR end_offset IS NULL OR start_offset < end_offset);

CREATE INDEX idx_customer_service_child_parent
    ON customer_service.document_chunk (parent_id, child_no);
