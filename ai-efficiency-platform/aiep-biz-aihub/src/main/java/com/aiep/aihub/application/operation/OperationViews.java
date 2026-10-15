package com.aiep.aihub.application.operation;

import java.time.LocalDateTime;
import java.util.List;

public final class OperationViews {
    private OperationViews() {
    }

    public record ConversationView(String conversationId, String title, String status, LocalDateTime createdAt) { }
    public record RunView(
            String conversationId,
            String runId,
            String agentRunId,
            String status,
            String failureCode,
            String failureMessage) { }
    public record ArtifactView(
            String artifactId,
            String conversationId,
            String runId,
            String artifactType,
            String platform,
            int version,
            String title,
            String bodyMarkdown,
            String bodyHtml,
            LocalDateTime createdAt) { }
    public record ArtifactSummary(
            String artifactId, String artifactType, String platform, int version, String title, LocalDateTime createdAt) { }
    public record ArtifactListView(String conversationId, List<ArtifactSummary> artifacts) { }
}
