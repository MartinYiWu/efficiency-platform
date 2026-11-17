package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public record MemoryCleanupRequest(
 @JsonProperty("event_id") String eventId,
 @JsonProperty("expected_execution_revision") long expectedExecutionRevision,
 @JsonProperty("grant_epoch") long grantEpoch,
 @JsonProperty("source_epoch") long sourceEpoch,
 @JsonProperty("deletion_epoch") long deletionEpoch,
 @JsonProperty("source_dependencies") List<MemoryContextPacket.Dependency> sourceDependencies) {
 public MemoryCleanupRequest{sourceDependencies=List.copyOf(sourceDependencies);}
}
