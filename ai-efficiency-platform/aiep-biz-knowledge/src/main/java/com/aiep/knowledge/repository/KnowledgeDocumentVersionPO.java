package com.aiep.knowledge.repository;

import java.time.LocalDate;
import java.time.LocalDateTime;

public record KnowledgeDocumentVersionPO(
        String id, String documentId, int versionNo, String fileId, String fileSha256,
        String contentType, String changeSummary, LocalDate effectiveDate, String status,
        String parseMetadata, String errorCode, String errorMessage, String createdBy,
        LocalDateTime createdAt, LocalDateTime publishedAt, String evidenceMode) {
    public KnowledgeDocumentVersionPO {
        evidenceMode = evidenceMode == null ? "FULL_ONLY" : evidenceMode;
    }

    public KnowledgeDocumentVersionPO(String id, String documentId, int versionNo, String fileId,
            String fileSha256, String contentType, String changeSummary, LocalDate effectiveDate,
            String status, String parseMetadata, String errorCode, String errorMessage,
            String createdBy, LocalDateTime createdAt, LocalDateTime publishedAt) {
        this(id, documentId, versionNo, fileId, fileSha256, contentType, changeSummary, effectiveDate,
                status, parseMetadata, errorCode, errorMessage, createdBy, createdAt, publishedAt, "FULL_ONLY");
    }
}
