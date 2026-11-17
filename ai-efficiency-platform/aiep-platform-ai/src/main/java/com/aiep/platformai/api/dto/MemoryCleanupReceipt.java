package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;

public record MemoryCleanupReceipt(
 @JsonProperty("execution_id") String executionId,
 @JsonProperty("event_id") String eventId,
 @JsonProperty("deletion_epoch") long deletionEpoch,
 Map<String,String> receipts) {
 public MemoryCleanupReceipt{receipts=Map.copyOf(receipts);}
}
