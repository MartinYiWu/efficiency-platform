package com.aiep.aihub.domain.operation;

import java.time.LocalDateTime;

public record OperationRun(
        String id,
        String conversationId,
        String tenantId,
        String userMessageId,
        String agentRunId,
        String status,
        long lastEventSequence,
        String failureCode,
        String failureMessage,
        LocalDateTime createdAt,
        LocalDateTime updatedAt) {
}
