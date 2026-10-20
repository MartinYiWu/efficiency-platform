package com.aiep.aihub.repository.management;

import java.time.LocalDateTime;

public record AiReleaseSnapshotPO(
        String id, String agentReleaseId, String snapshotJson, String checksum,
        String agentAckStatus, LocalDateTime agentAckAt, LocalDateTime createdAt) { }
