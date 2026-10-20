package com.aiep.knowledge.repository;

import java.time.LocalDateTime;

public record KnowledgeIngestItemPO(
        String id, String batchId, String fileId, String documentId,
        String documentVersionId, String status, String errorCode, String errorMessage,
        String retryOfItemId, LocalDateTime createdAt, LocalDateTime updatedAt,
        LocalDateTime finishedAt) {
}
