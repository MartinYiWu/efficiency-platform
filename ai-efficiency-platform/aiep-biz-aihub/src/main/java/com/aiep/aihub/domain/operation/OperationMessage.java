package com.aiep.aihub.domain.operation;

import java.time.LocalDateTime;

public record OperationMessage(
        String id,
        String conversationId,
        String tenantId,
        String role,
        String content,
        String runId,
        String clientRequestId,
        LocalDateTime createdAt) {
}
