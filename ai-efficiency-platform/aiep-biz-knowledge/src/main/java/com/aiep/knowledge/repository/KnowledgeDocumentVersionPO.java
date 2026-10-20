package com.aiep.knowledge.repository;

import java.time.LocalDate;
import java.time.LocalDateTime;

public record KnowledgeDocumentVersionPO(
        String id, String documentId, int versionNo, String fileId, String fileSha256,
        String contentType, String changeSummary, LocalDate effectiveDate, String status,
        String parseMetadata, String errorCode, String errorMessage, String createdBy,
        LocalDateTime createdAt, LocalDateTime publishedAt) {
}
