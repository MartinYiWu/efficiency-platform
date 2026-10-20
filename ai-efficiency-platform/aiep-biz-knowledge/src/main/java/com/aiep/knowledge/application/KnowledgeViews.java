package com.aiep.knowledge.application;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

public final class KnowledgeViews {
    private KnowledgeViews() {
    }

    public record PageView<T>(List<T> items, int page, int pageSize, long total) { }
    public record KnowledgeBaseView(
            String id, String code, String name, String description, String knowledgeType,
            String visibilityScope, String status, String currentIndexReleaseId,
            LocalDateTime createdAt, LocalDateTime updatedAt) { }
    public record DirectoryView(
            String id, String knowledgeBaseId, String parentId, String name, String path,
            int sortNo, String status) { }
    public record DocumentView(
            String id, String knowledgeBaseId, String directoryId, String title,
            String documentCode, String sourceType, String status,
            String currentPublishedVersionId, List<DocumentVersionView> versions) { }
    public record DocumentVersionView(
            String id, String documentId, int versionNo, String fileId, String fileSha256,
            String contentType, String changeSummary, LocalDate effectiveDate, String status,
            String errorCode, String errorMessage, LocalDateTime createdAt,
            List<ProcessingTaskView> processingTasks) { }
    public record IngestBatchView(
            String id, String knowledgeBaseId, String importMode, int totalCount,
            int succeededCount, int failedCount, String status,
            LocalDateTime createdAt, LocalDateTime finishedAt, List<IngestItemView> items) { }
    public record IngestItemView(
            String id, String batchId, String fileId, String documentId,
            String documentVersionId, String status, String errorCode,
            String errorMessage, String retryOfItemId) { }
    public record ProcessingTaskView(
            String id, String documentVersionId, String agentTaskId, String stage,
            String status, int attemptNo, int progressPercent, String errorCode,
            String errorMessage, LocalDateTime startedAt, LocalDateTime finishedAt) { }
}
