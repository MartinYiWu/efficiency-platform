package com.aiep.knowledge.repository;

import java.time.LocalDateTime;

public record KnowledgeIngestBatchPO(
        String id, String knowledgeBaseId, String importMode, int totalCount,
        int succeededCount, int failedCount, String status, String createdBy,
        LocalDateTime createdAt, LocalDateTime finishedAt) {
}
