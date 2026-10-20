package com.aiep.knowledge.repository;

import java.time.LocalDateTime;

public record KnowledgeIndexReleaseDocumentPO(
        String indexReleaseId, String documentId, String documentVersionId,
        String documentSha256, LocalDateTime createdAt) {
}
