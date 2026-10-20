package com.aiep.knowledge.repository;

import java.time.LocalDateTime;

public record KnowledgeBasePO(
        String id, String tenantId, String code, String name, String description,
        String knowledgeType, String visibilityScope, String ownerDepartmentId,
        String status, String currentIndexReleaseId, String createdBy,
        LocalDateTime createdAt, String updatedBy, LocalDateTime updatedAt) {
}
