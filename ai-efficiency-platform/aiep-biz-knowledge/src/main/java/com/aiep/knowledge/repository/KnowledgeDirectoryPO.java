package com.aiep.knowledge.repository;

import java.time.LocalDateTime;

public record KnowledgeDirectoryPO(
        String id, String knowledgeBaseId, String parentId, String name, String path,
        int sortNo, String status, String createdBy, LocalDateTime createdAt,
        String updatedBy, LocalDateTime updatedAt) {
}
