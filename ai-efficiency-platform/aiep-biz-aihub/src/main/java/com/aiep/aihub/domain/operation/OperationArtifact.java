package com.aiep.aihub.domain.operation;

import java.time.LocalDateTime;

public record OperationArtifact(
        String id,
        String conversationId,
        String runId,
        String sourceResearchRunId,
        String tenantId,
        String artifactType,
        String scenario,
        String platform,
        int versionNo,
        String rootArtifactId,
        String parentArtifactId,
        String title,
        String bodyMarkdown,
        String bodyHtml,
        String publicContent,
        String internalMetadata,
        LocalDateTime createdAt) {
}
