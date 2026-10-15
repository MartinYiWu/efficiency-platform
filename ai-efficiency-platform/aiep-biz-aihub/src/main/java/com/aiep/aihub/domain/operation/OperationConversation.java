package com.aiep.aihub.domain.operation;

import java.time.LocalDateTime;

public record OperationConversation(
        String id,
        String tenantId,
        String userId,
        String title,
        String status,
        String lastResearchRunId,
        LocalDateTime createdAt,
        LocalDateTime updatedAt) {
}
