-- 智能客服知识向量增量；不负责安装 vector 扩展。
CREATE SCHEMA customer_service;

CREATE TABLE customer_service.document_chunk (
    chunk_id UUID NOT NULL,
    tenant_id TEXT NOT NULL,
    knowledge_base_id UUID NOT NULL,
    document_id UUID NOT NULL,
    document_version_id UUID NOT NULL,
    document_title TEXT NOT NULL CHECK (length(btrim(document_title)) > 0),
    version_no INTEGER NOT NULL CHECK (version_no > 0),
    chunk_no INTEGER NOT NULL CHECK (chunk_no > 0),
    section_path TEXT,
    page_no INTEGER CHECK (page_no IS NULL OR page_no > 0),
    content TEXT NOT NULL CHECK (length(btrim(content)) > 0),
    content_hash CHAR(64) NOT NULL,
    token_count INTEGER NOT NULL CHECK (token_count > 0),
    embedding vector(1024) NOT NULL,
    embedding_model TEXT NOT NULL CHECK (embedding_model = 'text-embedding-v4'),
    embedding_dimension INTEGER NOT NULL CHECK (embedding_dimension = 1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id),
    UNIQUE (document_version_id, chunk_no)
);

CREATE INDEX idx_customer_service_chunk_embedding_hnsw
    ON customer_service.document_chunk
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_customer_service_chunk_content_fts
    ON customer_service.document_chunk
    USING gin (to_tsvector('simple', content));

CREATE INDEX idx_customer_service_chunk_scope
    ON customer_service.document_chunk (
        tenant_id,
        knowledge_base_id,
        document_version_id
    );

CREATE TABLE customer_service.index_release_document (
    index_release_id UUID NOT NULL,
    knowledge_base_id UUID NOT NULL,
    document_id UUID NOT NULL,
    document_version_id UUID NOT NULL,
    document_sha256 CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (index_release_id, document_id)
);

CREATE INDEX idx_customer_service_release_version
    ON customer_service.index_release_document (document_version_id);

CREATE INDEX idx_customer_service_release_scope
    ON customer_service.index_release_document (
        index_release_id,
        knowledge_base_id,
        document_version_id
    );
