package com.aiep.knowledge.repository;

import java.time.LocalDateTime;

public record KnowledgeDocumentPO(
        String id, String knowledgeBaseId, String directoryId, String title,
        String documentCode, String sourceType, String status,
        String currentPublishedVersionId, String createdBy, LocalDateTime createdAt,
        String updatedBy, LocalDateTime updatedAt) {
}
