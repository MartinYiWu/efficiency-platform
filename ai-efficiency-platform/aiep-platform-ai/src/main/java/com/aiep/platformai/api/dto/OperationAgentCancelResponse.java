package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public record OperationAgentCancelResponse(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("run_id") String runId,
        String status,
        boolean degraded,
        @JsonProperty("last_event_id") String lastEventId) {
}
