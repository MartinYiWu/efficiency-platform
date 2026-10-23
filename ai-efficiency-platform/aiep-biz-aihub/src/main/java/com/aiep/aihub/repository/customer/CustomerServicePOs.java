package com.aiep.aihub.repository.customer;

import java.time.Instant;

public final class CustomerServicePOs {
    private CustomerServicePOs() { }

    public record ConversationPO(
            String id, String tenantId, String userId, String title, String status,
            Instant lastMessageAt, Instant createdAt, Instant updatedAt) { }

    public record MessagePO(
            String id, String conversationId, String tenantId, String role, String content,
            String status, String answerMode, String runId, String clientRequestId,
            Instant createdAt) { }

    public record RunPO(
            String id, String conversationId, String tenantId, String userMessageId,
            String agentRunId, String agentReleaseId, String status, String answerMode,
            long lastEventSequence, String failureCode, String failureMessage,
            Instant startedAt, Instant finishedAt, Instant createdAt, Instant updatedAt) { }

    public record RunStepPO(
            String id, String runId, long sequenceNo, String stage, String status,
            String publicSummary, String internalPayload, Instant startedAt, Instant finishedAt) { }

    public record CitationPO(
            String id, String runId, String messageId, int citationNo, String knowledgeBaseId,
            String documentId, String documentVersionId, String indexReleaseId, String chunkId,
            String documentTitle, int versionNo, String sectionPath, Integer pageNo,
            String quotedText, String contentHash, Instant createdAt,
            String parentId, String citationType,
            java.util.List<com.aiep.platformai.api.dto.CustomerServiceEvidenceFacts.Span> originalSpans) {
        public CitationPO(String id, String runId, String messageId, int citationNo, String knowledgeBaseId,
                String documentId, String documentVersionId, String indexReleaseId, String chunkId,
                String documentTitle, int versionNo, String sectionPath, Integer pageNo,
                String quotedText, String contentHash, Instant createdAt) {
            this(id, runId, messageId, citationNo, knowledgeBaseId, documentId, documentVersionId,
                    indexReleaseId, chunkId, documentTitle, versionNo, sectionPath, pageNo,
                    quotedText, contentHash, createdAt, null, null, null);
        }
    }

    public record FeedbackPO(
            String id, String conversationId, String messageId, String runId, String tenantId,
            String userId, String rating, String reasonCode, String comment,
            Instant createdAt, Instant updatedAt) { }
}
