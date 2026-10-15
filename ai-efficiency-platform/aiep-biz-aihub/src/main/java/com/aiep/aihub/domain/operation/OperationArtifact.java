package com.aiep.aihub.domain.operation;

import java.time.LocalDateTime;

public record OperationArtifact(
        String id,
        String conversationId,
        String runId,
        String sourceResearchRunId,
        String tenantId,
        String artifactType,
        String platform,
        int versionNo,
        String title,
        String bodyMarkdown,
        String bodyHtml,
        String internalMetadata,
        LocalDateTime createdAt) {
}
