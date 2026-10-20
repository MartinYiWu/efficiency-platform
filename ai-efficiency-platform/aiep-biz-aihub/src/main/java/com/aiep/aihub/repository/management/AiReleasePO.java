package com.aiep.aihub.repository.management;

import java.time.LocalDateTime;

public record AiReleasePO(
        String id, String agentDefinitionId, String agentVersionId, String environment,
        String releaseStatus, String releaseSnapshotId, String releasedBy,
        LocalDateTime releasedAt, String rolledBackFromReleaseId, LocalDateTime createdAt) { }
