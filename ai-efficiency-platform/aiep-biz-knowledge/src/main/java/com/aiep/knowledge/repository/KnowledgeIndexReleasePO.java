package com.aiep.knowledge.repository;

import java.time.LocalDateTime;

public record KnowledgeIndexReleasePO(
        String id, String knowledgeBaseId, int releaseNo, String status,
        int documentCount, int chunkCount, String embeddingModel,
        int embeddingDimension, String checksum, String previousReleaseId,
        String createdBy, LocalDateTime createdAt, LocalDateTime publishedAt) {

    public KnowledgeIndexReleasePO withStatus(String value) {
        return new KnowledgeIndexReleasePO(
                id, knowledgeBaseId, releaseNo, value, documentCount, chunkCount,
                embeddingModel, embeddingDimension, checksum, previousReleaseId,
                createdBy, createdAt, publishedAt);
    }

    public KnowledgeIndexReleasePO ready(int documents, int chunks, String value) {
        return new KnowledgeIndexReleasePO(
                id, knowledgeBaseId, releaseNo, "READY", documents, chunks,
                embeddingModel, embeddingDimension, value, previousReleaseId,
                createdBy, createdAt, null);
    }

    public KnowledgeIndexReleasePO published() {
        return new KnowledgeIndexReleasePO(
                id, knowledgeBaseId, releaseNo, "PUBLISHED", documentCount, chunkCount,
                embeddingModel, embeddingDimension, checksum, previousReleaseId,
                createdBy, createdAt, LocalDateTime.now());
    }
}
