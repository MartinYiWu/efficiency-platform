package com.aiep.knowledge.repository;

import java.time.LocalDateTime;

public record KnowledgeProcessingTaskPO(
        String id, String documentVersionId, String agentTaskId, String stage,
        String status, int attemptNo, int progressPercent, String errorCode,
        String errorMessage, LocalDateTime startedAt, LocalDateTime finishedAt,
        LocalDateTime createdAt, LocalDateTime updatedAt) {
}
