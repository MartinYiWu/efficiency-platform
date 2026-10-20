package com.aiep.knowledge.domain;

public final class KnowledgeEnums {
    private KnowledgeEnums() {
    }

    public enum KnowledgeType { COMPANY_POLICY, BUSINESS_PROCESS, PRODUCT_DOCUMENTATION, TECHNICAL_DOCUMENTATION }
    public enum BaseStatus { DRAFT, ACTIVE, DISABLED }
    public enum DirectoryStatus { ACTIVE, DISABLED }
    public enum DocumentStatus { ACTIVE, ARCHIVED }
    public enum VersionStatus { DRAFT, PROCESSING, READY, PUBLISHED, RETIRED, FAILED }
    public enum BatchStatus { QUEUED, RUNNING, SUCCEEDED, PARTIAL_FAILED, FAILED, CANCELLED }
    public enum ItemStatus { QUEUED, PROCESSING, SUCCEEDED, FAILED, CANCELLED }
    public enum ProcessingStage { PREFLIGHT, PARSE, OCR, CHUNK, EMBED, VERIFY }
    public enum TaskStatus { QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED }
}
